"""Key-value genes: rule and regulator kinds under one `gene` keyword, sections, the 2025
dialect, lowering to RuleSet / RegulatoryGraph, diagnostics, action DSL, triggers."""
import pytest

from dnalang import Trigger, check, lower_all, parse, run_action
from dnalang.action_dsl import BudgetExceeded, DSLError, matches, subsumes, validate, parse_sexpr
from dnalang.rules_ir import LowerError, lower_regulation, lower_rules

CANON = """
organism sender {
  meta { version: "0.2", metrics: ["error", "cusum"] }
  gene a00 { id: "R0", condition: "00", action: "(send * s0)", expression: 1.0 }
  gene a01 { id: "R1", condition: "01", action: "(send * s1)" }
  gene detect { id: "G0", trigger: "when cusum > 8", action: "(emit shift)", outputs: ["shift"], cluster: "sense" }
  gene inject { id: "G1", trigger: "on_signal shift", action: "(seq (adjust inject 40) (adjust cusum_reset 1))",
                dependencies: ["G0"], cluster: "repair" }
  gene boost  { id: "G2", trigger: "after G1", action: "(adjust explore 0.8)", cluster: "repair" }
}
"""

LEGACY = """
ORGANISM QBYTE {
    META { version: "1.0.0", domain: "x", dfars: true }
    DNA { universal_constant: 2.176435e-8, purpose: "p" }
    METRICS { lambda: 0.95 }
    GENOME {
        GENE Alpha { id: "G0", expression: 1.0, trigger: "on_genesis", action: "(emit a)", dependencies: [], outputs: ["lattice"] }
        GENE Beta  { id: "G1", expression: 0.9, trigger: "after G0", action: "(emit b)", dependencies: ["G0"], outputs: [] }
    }
}
"""


def test_canonical_mixed_organism_parses_and_lowers():
    org = parse(CANON)
    assert [g.kind for g in org.kv_genes] == ["rule", "rule", "regulator", "regulator", "regulator"]
    assert org.meta["metrics"] == ["error", "cusum"]
    d = check(org)
    assert d.ok(), d.errors
    t = lower_all(org)
    assert t["circuit"] is None
    rs, rg = t["rules"], t["regulation"]
    assert rs.width == 2 and [r.id for r in rs.rules] == ["R0", "R1"]
    assert rs.rules[0].action == "(send * s0)"
    assert rg.order == ["G0", "G1", "G2"] and rg.regulators[1].dependencies == ["G0"]
    assert len(rs.sha256()) == 64 and rs.sha256() != rg.sha256()


def test_legacy_2025_dialect_parses():
    org = parse(LEGACY)
    assert org.name == "QBYTE" and org.meta["dfars"] is True
    assert org.sections["dna"]["universal_constant"] == 2.176435e-8
    assert org.sections["metrics"]["lambda"] == 0.95
    assert [g.name for g in org.kv_genes] == ["Alpha", "Beta"]
    assert check(org).ok()
    rg = lower_regulation(org)
    assert rg.order == ["G0", "G1"] and rg.regulators[0].trigger == "on_genesis"


def test_circuit_organisms_unchanged():
    org = parse(open("examples/dd_staggered_xy4.dna").read())
    assert org.kv_genes == [] and check(org).ok()
    assert lower_all(org)["circuit"].n_qubits == 4


def test_diagnostics():
    bad = parse('organism b { gene a { id: "A", trigger: "when x > 1", action: "(launch)" } }')
    d = check(bad)
    assert not d.ok() and "unknown op 'launch'" in d.errors[0]
    cyc = parse('''organism c {
        gene a { id: "A", trigger: "continuous", action: "(emit x)", dependencies: ["B"] }
        gene b { id: "B", trigger: "continuous", action: "(emit y)", dependencies: ["A"] } }''')
    with pytest.raises(LowerError, match="cycle"):
        lower_regulation(cyc)
    dup = parse('organism d { gene a { id: "A", trigger: "continuous", action: "(emit x)" } gene b { id: "A", trigger: "continuous", action: "(emit y)" } }')
    assert any("duplicate gene id" in e for e in check(dup).errors)
    wide = parse('organism e { gene a { condition: "01#", action: "(emit 1)" } gene b { condition: "0#", action: "(emit 0)" } }')
    with pytest.raises(LowerError, match="mixed widths"):
        lower_rules(wide)
    undeclared = parse('organism f { meta { metrics: ["error"] } gene a { trigger: "when cusum > 1", action: "(emit x)" } }')
    assert any("undeclared metric" in w for w in check(undeclared).warnings)


def test_action_dsl():
    ctx = run_action("(seq (set x (add (reg 0) (reg 1))) (if (eq (var x) 2) (emit 1) (emit 0)) (send B s3))", "11#0", last="s1")
    assert ctx.emits == ["1"] and ctx.sends == [("B", "s3")] and ctx.vars == {"x": 2.0}
    with pytest.raises(DSLError):
        validate(parse_sexpr("(launch missiles)"))
    with pytest.raises(BudgetExceeded):
        run_action("(seq " + "(emit 1) " * 100 + ")", "0", budget=64)
    assert matches("1#0#", "1101") and subsumes("1###", "1#0#")


def test_triggers():
    for text in ("on_genesis", "continuous", "on_error", "after G1", "on_signal shift", "when error >= 0.3"):
        t = Trigger.parse(text)
        assert Trigger.parse(t.render()).__dict__ == t.__dict__
    assert Trigger.parse("when cusum > 8").fires(5, {"cusum": 9.0}, set(), set())
    assert not Trigger.parse("after G1").fires(5, {}, set(), {"G0"})
    with pytest.raises(ValueError):
        Trigger.parse("whenever")
