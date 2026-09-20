"""Static checks and constant evaluation.

Checks performed:
  * every gene referenced by the genome exists, arity and qubit count match
  * every port used in a gene body is declared
  * genome instances bind ports to distinct physical qubits
  * parameter types: angle/int/duration; durations non-negative
  * classical bits unique
  * DD parity: within a gene, per port, the number of echo(X) and echo(Y) pulses
    must each be even, otherwise the gene's net action is a Pauli (warning `dd-parity`).
    This is the check that would have saved 30 s of QPU on 2026-09-20.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

from . import ast as A

GATE_ARITY = {  # op -> (n_params, n_qubits)
    "h": (0, 1), "x": (0, 1), "y": (0, 1), "z": (0, 1), "s": (0, 1), "t": (0, 1), "sx": (0, 1),
    "rx": (1, 1), "ry": (1, 1), "rz": (1, 1), "cx": (0, 2), "cz": (0, 2), "swap": (0, 2),
}

_FUNCS = {
    "pi": lambda: math.pi,
    "phi": lambda: (1 + 5 ** 0.5) / 2,
    "sqrt": math.sqrt,
}


class SemaError(Exception):
    pass


@dataclass
class Diagnostics:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.errors


def eval_expr(e: A.Expr, env: Dict[str, float]) -> float:
    if isinstance(e, A.Const):
        return e.value
    if isinstance(e, A.ParamRef):
        if e.name not in env:
            raise SemaError(f"{e.pos}: unknown parameter '{e.name}'")
        return env[e.name]
    if isinstance(e, A.BinOp):
        a, b = eval_expr(e.left, env), eval_expr(e.right, env)
        if e.op == "+": return a + b
        if e.op == "-": return a - b
        if e.op == "*": return a * b
        if e.op == "/":
            if b == 0:
                raise SemaError(f"{e.pos}: division by zero")
            return a / b
    if isinstance(e, A.Call):
        if e.name not in _FUNCS:
            raise SemaError(f"{e.pos}: unknown function '{e.name}'")
        return _FUNCS[e.name](*[eval_expr(a, env) for a in e.args])
    raise SemaError(f"unhandled expression {e!r}")


def check(org: A.Organism) -> Diagnostics:
    d = Diagnostics()
    genes = {}
    for g in org.genes:
        if g.name in genes:
            d.errors.append(f"{g.pos}: duplicate gene '{g.name}'")
        genes[g.name] = g
        ports = set(g.ports)
        if len(ports) != len(g.ports):
            d.errors.append(f"{g.pos}: gene '{g.name}' declares a port twice")
        pnames = [p.name for p in g.params]
        if len(set(pnames)) != len(pnames):
            d.errors.append(f"{g.pos}: gene '{g.name}' declares a parameter twice")
        echo_x: Dict[str, int] = {p: 0 for p in g.ports}
        echo_y: Dict[str, int] = {p: 0 for p in g.ports}
        for s in g.body:
            qs = [s.qubit] if isinstance(s, A.Measure) else s.qubits
            for q in qs:
                if q not in ports:
                    d.errors.append(f"{s.pos}: port '{q}' not declared in gene '{g.name}'")
            if isinstance(s, A.Gate):
                np_, nq = GATE_ARITY[s.op]
                if len(s.args) != np_:
                    d.errors.append(f"{s.pos}: {s.op} takes {np_} parameter(s), got {len(s.args)}")
                if len(s.qubits) != nq:
                    d.errors.append(f"{s.pos}: {s.op} acts on {nq} qubit(s), got {len(s.qubits)}")
                if nq == 2 and len(set(s.qubits)) == 1:
                    d.errors.append(f"{s.pos}: {s.op} needs two distinct qubits")
            elif isinstance(s, A.Echo):
                for q in s.qubits:
                    if q in echo_x:
                        (echo_x if s.pauli == "X" else echo_y)[q] += 1
        for p in g.ports:
            if echo_x[p] % 2 or echo_y[p] % 2:
                d.warnings.append(
                    f"{g.pos}: dd-parity: gene '{g.name}' port '{p}' has "
                    f"{echo_x[p]} X and {echo_y[p]} Y echoes; net action is a Pauli, not identity")
    # genome
    used_q: Dict[int, str] = {}
    cbits: List[str] = []
    for inst in org.genome:
        g = genes.get(inst.gene)
        if g is None:
            d.errors.append(f"{inst.pos}: unknown gene '{inst.gene}'"); continue
        if len(inst.args) != len(g.params):
            d.errors.append(f"{inst.pos}: gene '{g.name}' takes {len(g.params)} arg(s), got {len(inst.args)}")
        if len(inst.qubits) != len(g.ports):
            d.errors.append(f"{inst.pos}: gene '{g.name}' has {len(g.ports)} port(s), got {len(inst.qubits)} qubits")
        if len(set(inst.qubits)) != len(inst.qubits):
            d.errors.append(f"{inst.pos}: instance binds the same qubit to two ports")
        for q in inst.qubits:
            if q < 0:
                d.errors.append(f"{inst.pos}: negative qubit index {q}")
        try:
            env = {p.name: eval_expr(a, {}) for p, a in zip(g.params, inst.args)}
        except SemaError as e:
            d.errors.append(str(e)); env = {}
        for p in g.params:
            v = env.get(p.name)
            if v is None:
                continue
            if p.type == "int" and v != int(v):
                d.errors.append(f"{inst.pos}: parameter '{p.name}' must be an integer")
            if p.type == "duration" and v < 0:
                d.errors.append(f"{inst.pos}: duration '{p.name}' must be non-negative")
        # classical bits are namespaced per instance
        for s in g.body:
            if isinstance(s, A.Measure):
                name = f"{inst.gene}{len(cbits)}_{s.cbit}"
                cbits.append(name)
        for q in inst.qubits:
            used_q[q] = inst.gene
    org.cbits = cbits
    if not org.genome:
        d.errors.append(f"{org.pos}: genome is empty")
    return d
