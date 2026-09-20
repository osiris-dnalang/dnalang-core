import math
from pathlib import Path

import pytest

from dnalang import check, lower, parse, strip_barriers
from dnalang.parser import ParseError
from dnalang.sema import SemaError

EX = Path(__file__).parent.parent / "examples"


def test_parse_bell_example():
    org = parse((EX / "bell.dna").read_text())
    assert org.name == "Bell" and [g.name for g in org.genes] == ["bell_pair"]
    assert org.meta["author"] == "Devin Phillip Davis"


def test_biological_and_plain_spellings_are_the_same_gate():
    a = lower(parse("organism A { gene g() on q { helix q; twist(1.5) q; cleave q -> c; } genome { g() @ [0]; } }"))
    b = lower(parse("organism B { gene g() on q { h q; rz(1.5) q; cleave q -> c; } genome { g() @ [0]; } }"))
    assert strip_barriers(a).canonical() == strip_barriers(b).canonical()


def test_lower_bell():
    circ = strip_barriers(lower(parse((EX / "bell.dna").read_text())))
    assert [(o.name, o.qubits) for o in circ.ops] == [("h", (0,)), ("cx", (0, 1)), ("measure", (0,)), ("measure", (1,))]
    assert circ.n_cbits == 2 and circ.two_qubit_count() == 1 and circ.depth() == 3


def test_parameters_and_units():
    circ = strip_barriers(lower(parse((EX / "ghz.dna").read_text())))
    rz = [o for o in circ.ops if o.name == "rz"]
    assert len(rz) == 4 and all(math.isclose(o.params[0], -math.pi / 4) for o in rz)
    dd = strip_barriers(lower(parse((EX / "dd_staggered_xy4.dna").read_text())))
    per_q = {}
    for o in dd.ops:
        if o.name == "delay":
            per_q[o.qubits[0]] = per_q.get(o.qubits[0], 0.0) + o.duration_s
    assert all(math.isclose(v, 16e-6, rel_tol=1e-9) for v in per_q.values())


def test_unknown_port_is_an_error():
    d = check(parse("organism A { gene g() on q { helix r; } genome { g() @ [0]; } }"))
    assert not d.ok() and "port 'r'" in d.errors[0]


def test_arity_errors():
    d = check(parse("organism A { gene g() on q { bond q, q; twist q; } genome { g() @ [0]; } }"))
    assert any("distinct" in e for e in d.errors) and any("1 parameter" in e for e in d.errors)


def test_genome_binding_errors():
    d = check(parse("organism A { gene g() on a, b { bond a, b; } genome { g() @ [0]; } }"))
    assert any("2 port" in e for e in d.errors)
    d = check(parse("organism A { gene g() on a, b { bond a, b; } genome { g() @ [1, 1]; } }"))
    assert any("same qubit" in e for e in d.errors)


def test_dd_parity_warning():
    src = "organism A { gene g(T: duration) on q { helix q; wait(T/2) q; echo(Y) q; wait(T/2) q; helix q; cleave q -> c; } genome { g(10us) @ [0]; } }"
    d = check(parse(src))
    assert d.ok() and any("dd-parity" in w for w in d.warnings)
    src_ok = src.replace("echo(Y) q; wait(T/2) q;", "echo(Y) q; wait(T/4) q; echo(Y) q; wait(T/4) q;")
    assert not check(parse(src_ok)).warnings


def test_missing_genome_is_a_parse_error():
    with pytest.raises(ParseError):
        parse("organism A { gene g() on q { helix q; } }")


def test_lower_refuses_invalid():
    with pytest.raises(SemaError):
        lower(parse("organism A { gene g() on q { helix r; } genome { g() @ [0]; } }"))


def test_qasm3_roundtrip_text():
    circ = strip_barriers(lower(parse((EX / "bell.dna").read_text())))
    q = circ.to_qasm3()
    assert "OPENQASM 3.0;" in q and "h q[0];" in q and "cx q[0], q[1];" in q and "c[1] = measure q[1];" in q
