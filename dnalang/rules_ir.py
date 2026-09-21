"""Lowering targets for key-value genes.

``RuleSet``          the rule genes of an organism as data: (id, condition, action, expression,
                     cluster), with a fixed register width — the input of a Learning Classifier
                     System.
``RegulatoryGraph``  the regulator genes as a dependency graph with a topological expression
                     order (cycles are an error) — the input of a regulatory-network runtime.

Both are pure data with a canonical JSON form and a sha256, so a compiled organism can be
cited by hash exactly like a circuit.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from . import ast as A
from .action_dsl import DSLError, parse_sexpr, to_sexpr, validate
from .regulation import Trigger


class LowerError(ValueError):
    pass


@dataclass
class Rule:
    id: str
    name: str
    condition: str
    action: str
    expression: float = 1.0
    cluster: str = "default"


@dataclass
class RuleSet:
    organism: str
    width: int
    rules: List[Rule] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"organism": self.organism, "width": self.width, "rules": [asdict(r) for r in self.rules]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()


@dataclass
class Regulator:
    id: str
    name: str
    trigger: str
    action: str
    dependencies: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    cluster: str = "default"


@dataclass
class RegulatoryGraph:
    organism: str
    regulators: List[Regulator] = field(default_factory=list)
    order: List[str] = field(default_factory=list)      # topological expression order

    def to_dict(self) -> Dict[str, Any]:
        return {"organism": self.organism, "order": list(self.order),
                "regulators": [asdict(r) for r in self.regulators]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()


def _gene_id(g: A.KVGene, i: int) -> str:
    return str(g.get("id", f"G{i}"))


def _action(g: A.KVGene) -> str:
    src = g.get("action")
    if not isinstance(src, str):
        raise LowerError(f"{g.pos}: gene '{g.name}' has no action")
    try:
        node = parse_sexpr(src)
        validate(node)
    except DSLError as e:
        raise LowerError(f"{g.pos}: gene '{g.name}' action: {e}")
    return to_sexpr(node)


def lower_rules(org: A.Organism) -> RuleSet:
    rules = org.rules
    if not rules:
        raise LowerError(f"organism '{org.name}' has no rule genes")
    widths = {len(str(g.get("condition"))) for g in rules}
    if len(widths) != 1:
        raise LowerError(f"organism '{org.name}': rule conditions have mixed widths {sorted(widths)}")
    out = RuleSet(org.name, widths.pop())
    for i, g in enumerate(org.kv_genes):
        if g.kind != "rule":
            continue
        cond = str(g.get("condition"))
        if any(c not in "01#" for c in cond):
            raise LowerError(f"{g.pos}: gene '{g.name}' condition must be over 0/1/#")
        out.rules.append(Rule(_gene_id(g, i), g.name, cond, _action(g),
                              float(g.get("expression", 1.0)), str(g.get("cluster", "default"))))
    return out


def lower_regulation(org: A.Organism) -> RegulatoryGraph:
    regs = org.regulators
    if not regs:
        raise LowerError(f"organism '{org.name}' has no regulator genes")
    out = RegulatoryGraph(org.name)
    ids: Dict[str, Regulator] = {}
    for i, g in enumerate(org.kv_genes):
        if g.kind != "regulator":
            continue
        try:
            trig = Trigger.parse(str(g.get("trigger"))).render()
        except ValueError as e:
            raise LowerError(f"{g.pos}: gene '{g.name}': {e}")
        r = Regulator(_gene_id(g, i), g.name, trig, _action(g),
                      [str(d) for d in (g.get("dependencies") or [])],
                      [str(o) for o in (g.get("outputs") or [])], str(g.get("cluster", "default")))
        if r.id in ids:
            raise LowerError(f"{g.pos}: duplicate gene id '{r.id}'")
        ids[r.id] = r
        out.regulators.append(r)
    for r in out.regulators:
        for d in r.dependencies:
            if d not in ids:
                raise LowerError(f"regulator '{r.name}' depends on unknown gene '{d}'")
        t = Trigger.parse(r.trigger)
        if t.kind == "after" and t.ref not in ids:
            raise LowerError(f"regulator '{r.name}' trigger refers to unknown gene '{t.ref}'")
    # topological order over dependencies; cycles are errors
    state: Dict[str, int] = {}
    order: List[str] = []

    def visit(i: str, path: List[str]):
        if state.get(i) == 2:
            return
        if state.get(i) == 1:
            raise LowerError("dependency cycle: " + " -> ".join(path + [i]))
        state[i] = 1
        for d in ids[i].dependencies:
            visit(d, path + [i])
        state[i] = 2
        order.append(i)
    for i in ids:
        visit(i, [])
    out.order = order
    return out


def lower_all(org: A.Organism) -> Dict[str, Optional[Any]]:
    """Every target the organism supports: circuit (if it has circuit genes and a genome),
    rules, regulation. Missing targets are None."""
    out: Dict[str, Optional[Any]] = {"circuit": None, "rules": None, "regulation": None}
    if org.genes and org.genome:
        from .lower import lower
        out["circuit"] = lower(org)
    if org.rules:
        out["rules"] = lower_rules(org)
    if org.regulators:
        out["regulation"] = lower_regulation(org)
    return out


__all__ = ["LowerError", "Rule", "RuleSet", "Regulator", "RegulatoryGraph",
           "lower_rules", "lower_regulation", "lower_all"]
