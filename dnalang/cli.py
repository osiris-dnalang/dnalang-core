"""dnalang CLI: parse | check | lower | qasm | run | rules | regulation | ir | verify-ledger"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import Ledger, check, lower, parse
from .lexer import LexError
from .parser import ParseError
from .sema import SemaError


def _load(path: str):
    try:
        return parse(Path(path).read_text())
    except (LexError, ParseError) as e:
        sys.exit(f"error: {e}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dnalang")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("parse", "check", "lower", "qasm", "run", "rules", "regulation", "ir"):
        p = sub.add_parser(name); p.add_argument("file")
        if name == "run":
            p.add_argument("--shots", type=int, default=1024); p.add_argument("--seed", type=int)
        if name == "qasm":
            p.add_argument("--dt", type=float)
    v = sub.add_parser("verify-ledger"); v.add_argument("path")
    a = ap.parse_args(argv)

    if a.cmd == "verify-ledger":
        bad = Ledger(Path(a.path)).verify()
        print("ledger OK" if bad is None else f"ledger BROKEN: {bad}"); return 0 if bad is None else 1
    org = _load(a.file)
    if a.cmd == "parse":
        print(f"organism {org.name}: {len(org.genes)} circuit genes, {len(org.rules)} rule genes, "
              f"{len(org.regulators)} regulator genes, {len(org.genome)} instances, meta={org.meta}"); return 0
    d = check(org)
    for w in d.warnings: print("warning:", w)
    for e in d.errors: print("error:", e)
    if a.cmd == "check" or d.errors:
        return 0 if d.ok() else 1
    if a.cmd in ("rules", "regulation", "ir"):
        from .rules_ir import LowerError, lower_all
        try:
            t = lower_all(org)
        except (LowerError, SemaError) as e:
            sys.exit(f"error: {e}")
        if a.cmd == "ir":
            print(json.dumps({k: (v.to_dict() if v is not None and k != "circuit" else
                                  ({"n_qubits": v.n_qubits, "ops": len(v.ops), "sha256": v.sha256()} if v is not None else None))
                              for k, v in t.items()}, indent=1)); return 0
        v = t[a.cmd]
        if v is None:
            sys.exit(f"error: organism has no {a.cmd} target")
        print(json.dumps(v.to_dict(), indent=1)); print(f"// sha256 {v.sha256()}"); return 0
    try:
        circ = lower(org)
    except SemaError as e:
        sys.exit(f"error: {e}")
    if a.cmd == "lower":
        print(f"{circ.n_qubits} qubits, {circ.n_cbits} cbits, {len(circ.ops)} ops, depth {circ.depth()}, 2q {circ.two_qubit_count()}, sha256 {circ.sha256()[:16]}")
        for o in circ.ops: print(" ", o.name, list(o.qubits), list(o.params) if o.params else "", f"{o.duration_s*1e9:.1f}ns" if o.duration_s else "", f"-> c{o.cbit}" if o.cbit is not None else "")
        return 0
    if a.cmd == "qasm":
        print(circ.to_qasm3(a.dt), end=""); return 0
    if a.cmd == "run":
        from .backends import aer
        counts = aer.run([circ], shots=a.shots, seed=a.seed)[0]
        print(json.dumps(dict(sorted(counts.items(), key=lambda kv: -kv[1])), indent=1)); return 0


if __name__ == "__main__":
    sys.exit(main())
