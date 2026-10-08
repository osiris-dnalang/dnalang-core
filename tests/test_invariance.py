"""The invariance audit exists because θ_lock = 51.843° was a 19-angle sweep over a parameter
the Bell state cannot see: RY(θ) on both halves of |Φ+⟩ is the identity. A symbolic check run
before the sweep would have said so for free."""
from pathlib import Path

import pytest

pytest.importorskip("sympy")
from dnalang import parse
from dnalang.cli import main
from dnalang.invariance import audit

EX = Path(__file__).parent.parent / "examples"


def verdicts(src: str, **kw):
    return {f.param: f.verdict for f in audit(parse(src), **kw).findings}


def test_symmetric_ry_on_a_bell_pair_is_an_identity():
    v = verdicts("""organism Lock {
      gene lock(theta: angle) on a, b { helix a; bond a, b; fold(theta) a; fold(theta) b;
                                        cleave a -> ca; cleave b -> cb; }
      genome { lock(0.9048) @ [0, 1]; } }""")
    assert v == {"lock.theta": "invariant"}


def test_one_sided_ry_on_a_bell_pair_is_measurable():
    v = verdicts("""organism Tilt {
      gene tilt(theta: angle) on a, b { helix a; bond a, b; fold(theta) a; cleave a -> ca; cleave b -> cb; }
      genome { tilt(0.9048) @ [0, 1]; } }""")
    assert v == {"tilt.theta": "depends"}


def test_tied_sweep_is_audited_apart_from_each_instance():
    # the same gene on both halves: each instance alone moves the outcomes, both together cannot
    v = verdicts("""organism Split {
      gene bell() on a, b { helix a; bond a, b; }
      gene tilt(theta: angle) on q { fold(theta) q; cleave q -> c; }
      genome { bell() @ [0, 1]; tilt(0.9) @ [0]; tilt(0.9) @ [1]; } }""")
    assert v == {"tilt.theta (all 2 instances)": "invariant",
                 "tilt.theta (instance 1)": "depends", "tilt.theta (instance 2)": "depends"}


def test_a_phase_before_a_z_measurement_is_invisible_but_not_in_a_ramsey_sequence():
    hidden = verdicts("organism P { gene g(t: angle) on q { helix q; twist(t) q; cleave q -> c; } genome { g(1.0) @ [0]; } }")
    ramsey = verdicts("organism R { gene g(t: angle) on q { helix q; twist(t) q; helix q; cleave q -> c; } genome { g(1.0) @ [0]; } }")
    assert hidden == {"g.t": "invariant"} and ramsey == {"g.t": "depends"}


def test_an_unused_angle_is_invariant():
    assert verdicts("organism U { gene g(t: angle) on q { helix q; cleave q -> c; } genome { g(pi()/4) @ [0]; } }") \
        == {"g.t": "invariant"}


def test_symbolic_statevector_matches_qiskit_on_every_gate():
    # a wrong matrix here would turn into a wrong verdict, so check the simulator itself
    quantum_info = pytest.importorskip("qiskit.quantum_info")
    from dnalang import lower, strip_barriers
    from dnalang.invariance import _distribution, _ops
    org = parse("""organism All {
      gene g(a: angle, b: angle) on p, q, r {
        h p; x q; y r; z p; s q; t r; sx p; rx(a) q; ry(b) r; rz(a + b) p;
        cx p, q; cz q, r; swap p, r; echo(X) q; echo(Y) r; ry(0.3) p; rx(-b) r; }
      genome { g(0.7, pi()/5) @ [0, 2, 5]; } }""")
    probs = _distribution(_ops(org, {}), [0, 2, 5])
    vals = {sum(bit << m for m, bit in enumerate(k)): complex(p.evalf(30)) for k, p in probs.items()}
    assert all(abs(v.imag) < 1e-20 for v in vals.values())
    ours = {i: v.real for i, v in vals.items()}
    circ = strip_barriers(lower(org))
    keep = sorted({q for o in circ.ops for q in o.qubits})
    ref = quantum_info.Statevector(circ.to_qiskit()).probabilities(qargs=keep)
    assert all(abs(ours.get(i, 0.0) - ref[i]) < 1e-9 for i in range(len(ref)))


def test_identities_that_need_simplification_are_still_proven():
    import sympy as sp

    from dnalang.invariance import _verdict
    t = sp.Symbol("theta", real=True)
    # d/dθ = -sin 2θ + 2 sin θ cos θ: zero, but not term by term
    assert _verdict({(0,): sp.cos(2 * t) / 2 + sp.sin(t) ** 2}, t) == \
        ("invariant", "dP/dθ simplifies to 0 for every outcome")
    assert _verdict({(0,): sp.cos(t) ** 2}, t)[0] == "depends"


def test_ghz_readout_phase_is_measurable():
    v = verdicts((EX / "ghz.dna").read_text())
    assert v["readout.phi (all 4 instances)"] == "depends"
    assert all(x == "depends" for x in v.values())


def test_durations_are_reported_not_audited():
    r = audit(parse((EX / "dd_staggered_xy4.dna").read_text()))
    assert r.findings == [] and r.skipped is None
    assert any(n.startswith("xy4x2.T (duration") for n in r.not_audited)


def test_mid_circuit_measurement_and_size_are_skipped_not_guessed():
    mid = audit(parse("organism M { gene g(t: angle) on q { helix q; cleave q -> c; twist(t) q; } genome { g(1.0) @ [0]; } }"))
    assert mid.skipped and "mid-circuit" in mid.skipped and mid.findings == []
    big = audit(parse((EX / "ghz.dna").read_text()), max_qubits=3)
    assert big.skipped and "max_qubits=3" in big.skipped


def test_cli_exit_codes(tmp_path, capsys):
    lock = tmp_path / "lock.dna"
    lock.write_text("""organism Lock {
      gene lock(theta: angle) on a, b { helix a; bond a, b; fold(theta) a; fold(theta) b;
                                        cleave a -> ca; cleave b -> cb; }
      genome { lock(0.9048) @ [0, 1]; } }""")
    assert main(["check", str(lock), "--invariance"]) == 1
    assert "lock.theta: invariant" in capsys.readouterr().out
    assert main(["check", str(EX / "ghz.dna"), "--invariance"]) == 0
    assert main(["check", str(EX / "ghz.dna"), "--invariance", "--max-qubits", "2"]) == 2
    assert main(["check", str(lock)]) == 0          # without the flag, check is unchanged
