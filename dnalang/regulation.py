"""Trigger grammar for regulatory genes.

    on_genesis | continuous | on_error | after <gene_id> | on_signal <name>
    | when <metric> (< | <= | > | >= | ==) <number>

Metric names are declared by the runtime that executes the organism (``meta { metrics:
[...] }`` may declare them for static checking); the language only fixes the syntax and
the evaluation rule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Set

OPS = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
       ">=": lambda a, b: a >= b, "==": lambda a, b: a == b}
_WHEN = re.compile(r"^when\s+([a-z_][a-z0-9_]*)\s*(<=|>=|==|<|>)\s*(-?[0-9.]+(?:e-?\d+)?)$")
KINDS = ("genesis", "continuous", "error", "after", "signal", "when")


@dataclass
class Trigger:
    kind: str
    ref: Optional[str] = None
    op: Optional[str] = None
    value: float = 0.0

    @classmethod
    def parse(cls, text: str) -> "Trigger":
        t = " ".join(text.strip().lower().split())
        if t in ("on_genesis", "genesis"):
            return cls("genesis")
        if t in ("continuous", "on_tick", "always"):
            return cls("continuous")
        if t == "on_error":
            return cls("error")
        if t.startswith("after "):
            return cls("after", ref=t.split(None, 1)[1].strip().upper())
        if t.startswith("on_signal "):
            return cls("signal", ref=t.split(None, 1)[1].strip())
        m = _WHEN.match(t)
        if m:
            return cls("when", ref=m.group(1), op=m.group(2), value=float(m.group(3)))
        raise ValueError(f"unknown trigger {text!r}")

    def render(self) -> str:
        return {"genesis": "on_genesis", "continuous": "continuous", "error": "on_error",
                "after": f"after {self.ref}", "signal": f"on_signal {self.ref}",
                "when": f"when {self.ref} {self.op} {self.value:g}"}[self.kind]

    def fires(self, tick: int, metrics: Dict[str, float], board: Set[str],
              expressed_last: Set[str]) -> bool:
        if self.kind == "genesis":
            return tick == 1
        if self.kind == "continuous":
            return True
        if self.kind == "error":
            return metrics.get("last_error", 0.0) >= 1.0
        if self.kind == "after":
            return self.ref in expressed_last
        if self.kind == "signal":
            return self.ref in board
        return OPS[self.op](metrics.get(self.ref, 0.0), self.value)


__all__ = ["Trigger", "OPS", "KINDS"]
