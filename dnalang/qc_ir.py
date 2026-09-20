"""Flat circuit IR: a list of operations on physical qubits with durations in seconds.

Deliberately small. It converts losslessly to a Qiskit QuantumCircuit and to
OpenQASM 3 text; those are the only two consumers.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

ONE_Q = {"h", "x", "y", "z", "s", "t", "sx", "rx", "ry", "rz"}
TWO_Q = {"cx", "cz", "swap"}


@dataclass
class Op:
    name: str                       # gate name | delay | barrier | measure
    qubits: Tuple[int, ...]
    params: Tuple[float, ...] = ()
    duration_s: Optional[float] = None   # delay only
    cbit: Optional[int] = None           # measure only


@dataclass
class Circuit:
    n_qubits: int
    n_cbits: int
    ops: List[Op] = field(default_factory=list)
    name: str = "circuit"

    # --- introspection ------------------------------------------------------
    def count(self, name: str) -> int:
        return sum(1 for o in self.ops if o.name == name)

    def two_qubit_count(self) -> int:
        return sum(1 for o in self.ops if o.name in TWO_Q)

    def depth(self) -> int:
        level = [0] * self.n_qubits
        d = 0
        for o in self.ops:
            if o.name == "barrier":
                continue
            t = max(level[q] for q in o.qubits) + 1
            for q in o.qubits:
                level[q] = t
            d = max(d, t)
        return d

    def canonical(self) -> str:
        return json.dumps(
            [[o.name, list(o.qubits), [round(p, 12) for p in o.params], o.duration_s, o.cbit] for o in self.ops],
            separators=(",", ":"))

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()

    # --- exporters ------------------------------------------------------------
    def to_qiskit(self, dt: Optional[float] = None):
        """Return a qiskit.QuantumCircuit. Delays are emitted in dt if `dt` is given, else in seconds."""
        from qiskit import QuantumCircuit
        qc = QuantumCircuit(self.n_qubits, self.n_cbits, name=self.name)
        for o in self.ops:
            if o.name == "delay":
                if dt is not None:
                    qc.delay(int(round(o.duration_s / dt)), o.qubits[0], unit="dt")
                else:
                    qc.delay(o.duration_s, o.qubits[0], unit="s")
            elif o.name == "barrier":
                qc.barrier(*o.qubits)
            elif o.name == "measure":
                qc.measure(o.qubits[0], o.cbit)
            else:
                getattr(qc, o.name)(*o.params, *o.qubits)
        return qc

    def to_qasm3(self, dt: Optional[float] = None) -> str:
        lines = ["OPENQASM 3.0;", 'include "stdgates.inc";',
                 f"qubit[{self.n_qubits}] q;", f"bit[{self.n_cbits}] c;"]
        for o in self.ops:
            qs = ", ".join(f"q[{i}]" for i in o.qubits)
            if o.name == "delay":
                if dt is not None:
                    lines.append(f"delay[{int(round(o.duration_s / dt))}dt] {qs};")
                else:
                    lines.append(f"delay[{o.duration_s * 1e9:.3f}ns] {qs};")
            elif o.name == "barrier":
                lines.append(f"barrier {qs};")
            elif o.name == "measure":
                lines.append(f"c[{o.cbit}] = measure {qs};")
            elif o.params:
                ps = ", ".join(f"{p:.12g}" for p in o.params)
                lines.append(f"{o.name}({ps}) {qs};")
            else:
                lines.append(f"{o.name} {qs};")
        return "\n".join(lines) + "\n"
