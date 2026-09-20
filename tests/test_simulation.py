"""These tests exist because the previous runtime returned uniform random counts for a Bell
circuit and nobody noticed. A simulator that cannot make a Bell state is not a simulator."""
import math
from pathlib import Path

import pytest

pytest.importorskip("qiskit_aer")
from dnalang import lower, parse
from dnalang.backends import aer
from dnalang.metrics import ghz_fidelity, survival_plus, w2_marginal, bootstrap_ci

EX = Path(__file__).parent.parent / "examples"


def test_bell_is_fifty_fifty():
    circ = lower(parse((EX / "bell.dna").read_text()))
    counts = aer.run([circ], shots=4000, seed=1)[0]
    assert set(counts) <= {"00", "11"}
    assert abs(counts["00"] / 4000 - 0.5) < 0.05


def test_ghz_fidelity_is_one_noiselessly_for_any_phase():
    n = 4
    K = 2 * n + 2
    def org(phi, basis):
        ro = f"twist({-phi:.12f}) q; helix q; cleave q -> c;" if basis == "P" else "cleave q -> c;"
        return f"""organism G {{
          gene prep() on a, b, c, d {{ helix a; bond a, b; bond b, c; bond c, d; }}
          gene ro() on q {{ {ro} }}
          genome {{ prep() @ [0,1,2,3]; ro() @ [0]; ro() @ [1]; ro() @ [2]; ro() @ [3]; }} }}"""
    circs = [lower(parse(org(0.0, "Z")))] + [lower(parse(org(2 * math.pi * k / K, "P"))) for k in range(K)]
    counts = aer.run(circs, shots=2000, seed=3)
    F, ppop, C = ghz_fidelity(counts[0], counts[1:], n)
    assert ppop == 1.0 and abs(C - 1.0) < 0.03 and abs(F - 1.0) < 0.02
    # a GHZ state with an extra relative phase must score identically (this is why the tetrahedral RZ test was fair)
    circs2 = [lower(parse(org(0.0, "Z").replace("bond c, d;", "bond c, d; twist(0.7) d;")))] + \
             [lower(parse(org(2 * math.pi * k / K, "P").replace("bond c, d;", "bond c, d; twist(0.7) d;"))) for k in range(K)]
    F2, _, _ = ghz_fidelity(*[aer.run(circs2, shots=2000, seed=4)[0]], aer.run(circs2, shots=2000, seed=4)[1:], n)
    assert abs(F2 - 1.0) < 0.02


def test_survival_and_w2():
    circ = lower(parse((EX / "dd_staggered_xy4.dna").read_text()))
    c1, c2 = aer.run([circ, circ], shots=2000, seed=5)
    assert survival_plus(c1, range(4), 4) > 0.99          # noiseless: |+> survives the window
    assert w2_marginal(c1, c2, 4) < 0.1
    m, lo, hi = bootstrap_ci([0.5, 0.6, 0.55, 0.52])
    assert lo <= m <= hi
