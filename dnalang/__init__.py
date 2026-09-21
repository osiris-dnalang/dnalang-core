"""dna::}{::lang — a genome language for evolvable programs.

One grammar, three kinds of gene under one keyword, three lowering targets:
  circuit genes   (parameterised gate sequences)  → Circuit          (qc_ir, Aer/IBM backends)
  rule genes      (ternary condition + action)     → RuleSet          (Learning Classifier Systems)
  regulator genes (trigger + action + wiring)      → RegulatoryGraph  (regulatory-network runtimes)
plus the closed action DSL, the trigger grammar, evolutionary search, and a tamper-evident
run ledger. Runtimes (organism_sim, bridge) consume the targets; the language imports nothing
from them."""
from .parser import parse            # noqa: F401
from .sema import check              # noqa: F401
from .lower import lower, strip_barriers  # noqa: F401
from .qc_ir import Circuit, Op       # noqa: F401
from .ledger import Ledger           # noqa: F401
from .rules_ir import RuleSet, RegulatoryGraph, lower_rules, lower_regulation, lower_all  # noqa: F401
from .action_dsl import parse_sexpr, to_sexpr, validate, Interpreter, Context, run_action  # noqa: F401
from .regulation import Trigger      # noqa: F401

__version__ = "0.2.0"
