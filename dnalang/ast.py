"""AST for dnalang.

An *organism* is a named collection of *gene* templates plus a *genome* that
instantiates genes on physical qubits. Genes are parameterized sub-circuits with
typed formal qubit ports. Nothing here is executed; it is data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass(frozen=True)
class Pos:
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.line}:{self.col}"


# --- expressions -----------------------------------------------------------
@dataclass
class Const:
    value: float
    pos: Pos


@dataclass
class ParamRef:
    name: str
    pos: Pos


@dataclass
class BinOp:
    op: str  # + - * /
    left: "Expr"
    right: "Expr"
    pos: Pos


@dataclass
class Call:
    name: str  # pi, phi, sqrt
    args: List["Expr"]
    pos: Pos


Expr = Union[Const, ParamRef, BinOp, Call]


# --- statements -------------------------------------------------------------
@dataclass
class Gate:
    op: str                 # canonical IR name: h, x, y, z, s, t, sx, rx, ry, rz, cx, cz, swap
    args: List[Expr]
    qubits: List[str]       # port names
    pos: Pos


@dataclass
class Wait:
    duration: Expr          # seconds
    qubits: List[str]
    pos: Pos


@dataclass
class Echo:
    pauli: str              # X or Y
    qubits: List[str]
    pos: Pos


@dataclass
class Measure:
    qubit: str
    cbit: str
    pos: Pos


@dataclass
class Barrier:
    qubits: List[str]
    pos: Pos


Stmt = Union[Gate, Wait, Echo, Measure, Barrier]


# --- declarations -------------------------------------------------------------
@dataclass
class Param:
    name: str
    type: str               # angle | duration | int
    pos: Pos


@dataclass
class Gene:
    name: str
    params: List[Param]
    ports: List[str]
    body: List[Stmt]
    pos: Pos


@dataclass
class GeneInstance:
    gene: str
    args: List[Expr]
    qubits: List[int]
    pos: Pos


@dataclass
class Organism:
    name: str
    meta: dict
    genes: List[Gene]
    genome: List[GeneInstance]
    fitness: Optional[str]
    cbits: List[str] = field(default_factory=list)   # filled by sema, in declaration order
    pos: Optional[Pos] = None
