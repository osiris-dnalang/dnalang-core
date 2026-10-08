"""Pre-execution invariance audit: can a sweep over this parameter measure anything at all?

Before shots are spent sweeping a circuit parameter, check whether the outcome distribution
depends on it. Each angle argument of the genome is kept exact and symbolic (``pi()``,
``sqrt``, decimal constants as rationals), the noiseless statevector is computed in SymPy,
and every measured-outcome probability is differentiated with respect to the parameter. If
dP/dθ is identically zero for every outcome, no metric computed from counts can move when θ
is swept, on any device, and a "peak" in such a sweep is noise: a mathematical identity, not
physics (governance directive 1).

The case this exists for: RY(θ) applied to both halves of a Bell pair leaves |Φ+⟩ unchanged,
so the θ_lock = 51.843° sweep measured nothing (retracted).

Scope, stated rather than hidden:
  * noiseless and unitary. A delay is the identity, so duration parameters are reported as
    not audited: whatever they do happens only under noise. Integer parameters are discrete
    and are not audited either.
  * measurements must be terminal (no gate on a qubit after it is measured).
  * the symbolic statevector is exponential in the number of qubits, so circuits larger than
    ``max_qubits`` are not audited.
  * a parameter shared by several genome instances is audited once tied (every instance
    moves together, as a sweep usually does) and once per instance.

Requires SymPy: ``pip install 'dnalang[sym]'``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import ast as A
from .sema import SemaError, check

# Generic angles (radians) at which a derivative is evaluated before any simplification is
# attempted. A nonzero value at any of them proves dependence; fixed for reproducibility.
SCREEN_POINTS = ("0.37", "1.13", "2.29", "3.71", "4.43", "5.81", "6.07")
ZERO = 1e-20          # |dP/dθ| below this, evaluated to 30 digits, counts as zero at that point


@dataclass
class Finding:
    param: str        # gene.param, with the instance or "all instances" when a gene repeats
    verdict: str      # "invariant" | "depends" | "undetermined"
    proof: str        # how the verdict was reached


@dataclass
class Audit:
    n_qubits: int = 0
    findings: List[Finding] = field(default_factory=list)
    not_audited: List[str] = field(default_factory=list)
    skipped: Optional[str] = None      # why the audit could not run at all

    def invariant(self) -> List[Finding]:
        return [f for f in self.findings if f.verdict == "invariant"]

    def undetermined(self) -> List[Finding]:
        return [f for f in self.findings if f.verdict == "undetermined"]


class _Skip(Exception):
    pass


def _exact(e: A.Expr, env: Dict[str, object]):
    """Exact SymPy value of an expression (``sema.eval_expr`` evaluates to floats)."""
    import sympy as sp
    if isinstance(e, A.Const):
        return sp.Rational(repr(float(e.value)))
    if isinstance(e, A.ParamRef):
        return env[e.name]
    if isinstance(e, A.BinOp):
        a, b = _exact(e.left, env), _exact(e.right, env)
        if e.op == "+": return a + b
        if e.op == "-": return a - b
        if e.op == "*": return a * b
        if e.op == "/": return a / b
    if isinstance(e, A.Call):
        args = [_exact(x, env) for x in e.args]
        if e.name == "pi": return sp.pi
        if e.name == "phi": return (1 + sp.sqrt(5)) / 2
        if e.name == "sqrt": return sp.sqrt(*args)
    raise SemaError(f"unhandled expression {e!r}")


def _matrix(name: str, args: list):
    import sympy as sp
    j, half = sp.I, sp.Rational(1, 2)
    if name in ("rx", "ry"):
        c, s = sp.cos(args[0] * half), sp.sin(args[0] * half)
        return ((c, -j * s), (-j * s, c)) if name == "rx" else ((c, -s), (s, c))
    if name == "rz":
        return ((sp.exp(-j * args[0] * half), 0), (0, sp.exp(j * args[0] * half)))
    r = 1 / sp.sqrt(2)
    return {
        "h": ((r, r), (r, -r)), "x": ((0, 1), (1, 0)), "y": ((0, -j), (j, 0)),
        "z": ((1, 0), (0, -1)), "s": ((1, 0), (0, j)), "t": ((1, 0), (0, sp.exp(j * sp.pi / 4))),
        "sx": ((half * (1 + j), half * (1 - j)), (half * (1 - j), half * (1 + j))),
    }[name]


def _ops(org: A.Organism, bind: Dict[Tuple[int, str], object]) -> list:
    """The genome as (gate, qubits, exact args); ``bind`` overrides (instance, param) values.
    Waits and barriers are dropped: on a noiseless statevector both are the identity."""
    genes = {g.name: g for g in org.genes}
    ops = []
    for k, inst in enumerate(org.genome):
        g = genes[inst.gene]
        env = {p.name: bind[(k, p.name)] if (k, p.name) in bind else _exact(a, {})
               for p, a in zip(g.params, inst.args)}
        port = dict(zip(g.ports, inst.qubits))
        for s in g.body:
            if isinstance(s, A.Gate):
                ops.append((s.op, tuple(port[q] for q in s.qubits), [_exact(a, env) for a in s.args]))
            elif isinstance(s, A.Echo):
                ops += [(s.pauli.lower(), (port[q],), []) for q in s.qubits]
            elif isinstance(s, A.Measure):
                ops.append(("measure", (port[s.qubit],), []))
    return ops


def _distribution(ops: list, qubits: List[int]) -> dict:
    """Exact outcome probabilities of the measured qubits (all qubits if none is measured)."""
    import sympy as sp
    pos = {q: i for i, q in enumerate(qubits)}
    dim = 1 << len(qubits)
    psi = [sp.Integer(0)] * dim
    psi[0] = sp.Integer(1)
    measured: List[int] = []
    for name, qs, args in ops:
        if name == "measure":
            measured.append(pos[qs[0]])
            continue
        if any(pos[q] in measured for q in qs):
            raise _Skip(f"'{name}' acts on qubit {qs[0]} after it is measured (mid-circuit measurement)")
        b = [1 << pos[q] for q in qs]
        if name == "cx":
            for i in range(dim):
                if i & b[0] and not i & b[1]:
                    psi[i], psi[i | b[1]] = psi[i | b[1]], psi[i]
        elif name == "cz":
            for i in range(dim):
                if i & b[0] and i & b[1]:
                    psi[i] = -psi[i]
        elif name == "swap":
            for i in range(dim):
                if i & b[0] and not i & b[1]:
                    j = (i ^ b[0]) | b[1]
                    psi[i], psi[j] = psi[j], psi[i]
        else:
            (m00, m01), (m10, m11) = _matrix(name, args)
            for i in range(dim):
                if not i & b[0]:
                    a0, a1 = psi[i], psi[i | b[0]]
                    psi[i], psi[i | b[0]] = m00 * a0 + m01 * a1, m10 * a0 + m11 * a1
    keep = measured or list(range(len(qubits)))
    probs: dict = {}
    for i, amp in enumerate(psi):
        if amp != 0:
            key = tuple((i >> m) & 1 for m in keep)
            probs[key] = probs.get(key, 0) + sp.expand(amp * sp.conjugate(amp))
    return probs


def _verdict(probs: dict, theta) -> Tuple[str, str]:
    import sympy as sp
    derivs = [(k, sp.diff(p, theta)) for k, p in probs.items()]
    derivs = [(k, dp) for k, dp in derivs if dp != 0]
    if not derivs:
        return "invariant", "dP/dθ is exactly 0 for every outcome"
    for key, dp in derivs:
        for x in SCREEN_POINTS:
            v = complex(dp.subs(theta, sp.Rational(x)).evalf(30))
            if abs(v) > ZERO:
                bits = "".join(map(str, key))
                return "depends", f"dP({bits})/dθ = {v.real:.3g} at θ = {x}"
    for key, dp in derivs:
        if sp.simplify(dp) == 0:
            continue
        same = dp.equals(0)
        if same is False:
            return "depends", f"dP({''.join(map(str, key))})/dθ is not identically 0"
        if same is None:
            return "undetermined", (f"dP/dθ vanished at {len(SCREEN_POINTS)} points "
                                    "but SymPy could not prove it is 0")
    return "invariant", "dP/dθ simplifies to 0 for every outcome"


def audit(org: A.Organism, *, max_qubits: int = 8) -> Audit:
    """Audit every angle parameter of the genome; see the module docstring for the scope."""
    try:
        import sympy as sp
    except ImportError:
        return Audit(skipped="SymPy is not installed (pip install 'dnalang[sym]')")
    diag = check(org)
    if not diag.ok():
        raise SemaError("; ".join(diag.errors))
    genes = {g.name: g for g in org.genes}
    qubits = sorted({q for inst in org.genome for q in inst.qubits})
    out = Audit(n_qubits=len(qubits))
    slots: Dict[Tuple[str, str], List[int]] = {}
    for k, inst in enumerate(org.genome):
        for p in genes[inst.gene].params:
            if p.type == "angle":
                slots.setdefault((inst.gene, p.name), []).append(k)
            else:
                why = "a delay is the identity without noise" if p.type == "duration" else "discrete"
                note = f"{inst.gene}.{p.name} ({p.type}: {why})"
                if note not in out.not_audited:
                    out.not_audited.append(note)
    if not slots:
        return out
    if len(qubits) > max_qubits:
        out.skipped = f"{len(qubits)} qubits > max_qubits={max_qubits} (the symbolic statevector is exponential)"
        return out
    theta = sp.Symbol("theta", real=True)
    runs = []
    for (gene, p), ks in slots.items():
        if len(ks) > 1:
            runs.append((f"{gene}.{p} (all {len(ks)} instances)", p, ks))
        runs += [(f"{gene}.{p}" + (f" (instance {k})" if len(ks) > 1 else ""), p, [k]) for k in ks]
    for label, p, ks in runs:
        try:
            probs = _distribution(_ops(org, {(k, p): theta for k in ks}), qubits)
        except _Skip as e:
            out.skipped = str(e)
            out.findings = []
            return out
        out.findings.append(Finding(label, *_verdict(probs, theta)))
    return out
