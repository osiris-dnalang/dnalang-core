"""Recursive-descent parser for dnalang.

Grammar (EBNF; also in docs/LANGUAGE.md):

  organism   := "organism" IDENT "{" meta? gene* genome fitness? "}"
  meta       := "meta" "{" (IDENT ":" (STRING|NUMBER) ","?)* "}"
  gene       := "gene" IDENT "(" params? ")" "on" ports "{" stmt* "}"
  params     := param ("," param)*          param := IDENT ":" ("angle"|"duration"|"int")
  ports      := IDENT ("," IDENT)*
  stmt       := gateop args? qubits ";"
              | "wait" "(" expr ")" qubits ";"
              | "echo" "(" IDENT ")" qubits ";"
              | "cleave" IDENT "->" IDENT ";"
              | "barrier" qubits ";"
  args       := "(" expr ("," expr)* ")"
  qubits     := IDENT ("," IDENT)*
  genome     := "genome" "{" instance* "}"
  instance   := IDENT args? "@" "[" NUMBER ("," NUMBER)* "]" ";"
  fitness    := "fitness" IDENT ";"
  expr       := term (("+"|"-") term)*      term := unary (("*"|"/") unary)*
  unary      := "-" unary | primary
  primary    := NUMBER | IDENT | IDENT "(" (expr ("," expr)*)? ")" | "(" expr ")"
"""
from __future__ import annotations

from typing import List, Optional

from . import ast as A
from .lexer import GATE_ALIASES, Token, tokenize

_UNIT = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0}


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: List[Token]):
        self.toks = tokens
        self.i = 0

    # --- helpers ----------------------------------------------------------
    @property
    def cur(self) -> Token:
        return self.toks[self.i]

    def peek(self, k: int = 1) -> Token:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def err(self, msg: str, tok: Optional[Token] = None):
        tok = tok or self.cur
        raise ParseError(f"{tok.pos}: {msg} (got {tok.kind} {tok.text!r})")

    def accept(self, kind: str, text: Optional[str] = None) -> Optional[Token]:
        t = self.cur
        if t.kind == kind and (text is None or t.text == text):
            self.i += 1
            return t
        return None

    def expect(self, kind: str, text: Optional[str] = None) -> Token:
        t = self.accept(kind, text)
        if t is None:
            self.err(f"expected {text or kind}")
        return t

    def kw(self, word: str) -> Optional[Token]:
        return self.accept("KEYWORD", word)

    # --- grammar ------------------------------------------------------------
    def organism(self) -> A.Organism:
        start = self.cur
        if not self.kw("organism"):
            self.err("expected 'organism'")
        name = self.expect("IDENT").text
        self.expect("SYM", "{")
        meta = {}
        genes: List[A.Gene] = []
        genome: List[A.GeneInstance] = []
        fitness = None
        seen_genome = False
        while not self.accept("SYM", "}"):
            if self.kw("meta"):
                meta = self.meta()
            elif self.kw("gene"):
                genes.append(self.gene())
            elif self.kw("genome"):
                if seen_genome:
                    self.err("duplicate genome block")
                genome = self.genome(); seen_genome = True
            elif self.kw("fitness"):
                fitness = self.expect("IDENT").text
                self.expect("SYM", ";")
            else:
                self.err("expected meta, gene, genome or fitness")
        if not seen_genome:
            raise ParseError(f"{start.pos}: organism '{name}' has no genome block")
        self.expect("EOF")
        return A.Organism(name=name, meta=meta, genes=genes, genome=genome, fitness=fitness, pos=start.pos)

    def meta(self) -> dict:
        self.expect("SYM", "{")
        out = {}
        while not self.accept("SYM", "}"):
            key = self.expect("IDENT").text
            self.expect("SYM", ":")
            t = self.accept("STRING") or self.accept("NUMBER")
            if t is None:
                self.err("meta value must be a string or number")
            out[key] = t.text if t.kind == "STRING" else self._number(t)
            self.accept("SYM", ",")
        return out

    def gene(self) -> A.Gene:
        pos = self.cur.pos
        name = self.expect("IDENT").text
        params: List[A.Param] = []
        self.expect("SYM", "(")
        if not self.accept("SYM", ")"):
            while True:
                p = self.expect("IDENT")
                self.expect("SYM", ":")
                ty = self.cur
                if ty.kind != "KEYWORD" or ty.text not in ("angle", "duration", "int"):
                    self.err("parameter type must be angle, duration or int")
                self.i += 1
                params.append(A.Param(p.text, ty.text, p.pos))
                if self.accept("SYM", ")"):
                    break
                self.expect("SYM", ",")
        if not self.kw("on"):
            self.err("expected 'on' <ports>")
        ports = self.ident_list()
        self.expect("SYM", "{")
        body: List[A.Stmt] = []
        while not self.accept("SYM", "}"):
            body.append(self.stmt())
        return A.Gene(name, params, ports, body, pos)

    def ident_list(self) -> List[str]:
        out = [self.expect("IDENT").text]
        while self.accept("SYM", ","):
            out.append(self.expect("IDENT").text)
        return out

    def stmt(self) -> A.Stmt:
        t = self.cur
        if self.kw("wait"):
            self.expect("SYM", "(")
            d = self.expr()
            self.expect("SYM", ")")
            qs = self.ident_list()
            self.expect("SYM", ";")
            return A.Wait(d, qs, t.pos)
        if self.kw("echo"):
            self.expect("SYM", "(")
            p = self.expect("IDENT").text.upper()
            if p not in ("X", "Y"):
                self.err("echo pulse must be X or Y", t)
            self.expect("SYM", ")")
            qs = self.ident_list()
            self.expect("SYM", ";")
            return A.Echo(p, qs, t.pos)
        if self.kw("cleave"):
            q = self.expect("IDENT").text
            self.expect("ARROW")
            c = self.expect("IDENT").text
            self.expect("SYM", ";")
            return A.Measure(q, c, t.pos)
        if self.kw("barrier"):
            qs = self.ident_list()
            self.expect("SYM", ";")
            return A.Barrier(qs, t.pos)
        if t.kind == "IDENT" and t.text in GATE_ALIASES:
            self.i += 1
            args: List[A.Expr] = []
            if self.accept("SYM", "("):
                if not self.accept("SYM", ")"):
                    while True:
                        args.append(self.expr())
                        if self.accept("SYM", ")"):
                            break
                        self.expect("SYM", ",")
            qs = self.ident_list()
            self.expect("SYM", ";")
            return A.Gate(GATE_ALIASES[t.text], args, qs, t.pos)
        self.err("expected a statement")

    def genome(self) -> List[A.GeneInstance]:
        self.expect("SYM", "{")
        out: List[A.GeneInstance] = []
        while not self.accept("SYM", "}"):
            t = self.expect("IDENT")
            args: List[A.Expr] = []
            if self.accept("SYM", "("):
                if not self.accept("SYM", ")"):
                    while True:
                        args.append(self.expr())
                        if self.accept("SYM", ")"):
                            break
                        self.expect("SYM", ",")
            self.expect("SYM", "@")
            self.expect("SYM", "[")
            qs = [self._int(self.expect("NUMBER"))]
            while self.accept("SYM", ","):
                qs.append(self._int(self.expect("NUMBER")))
            self.expect("SYM", "]")
            self.expect("SYM", ";")
            out.append(A.GeneInstance(t.text, args, qs, t.pos))
        return out

    # --- expressions --------------------------------------------------------
    def expr(self) -> A.Expr:
        left = self.term()
        while self.cur.kind == "SYM" and self.cur.text in "+-":
            op = self.cur; self.i += 1
            left = A.BinOp(op.text, left, self.term(), op.pos)
        return left

    def term(self) -> A.Expr:
        left = self.unary()
        while self.cur.kind == "SYM" and self.cur.text in "*/":
            op = self.cur; self.i += 1
            left = A.BinOp(op.text, left, self.unary(), op.pos)
        return left

    def unary(self) -> A.Expr:
        t = self.cur
        if t.kind == "SYM" and t.text == "-":
            self.i += 1
            return A.BinOp("-", A.Const(0.0, t.pos), self.unary(), t.pos)
        return self.primary()

    def primary(self) -> A.Expr:
        t = self.cur
        if t.kind == "NUMBER":
            self.i += 1
            return A.Const(self._number(t), t.pos)
        if t.kind == "IDENT":
            self.i += 1
            if self.accept("SYM", "("):
                args: List[A.Expr] = []
                if not self.accept("SYM", ")"):
                    while True:
                        args.append(self.expr())
                        if self.accept("SYM", ")"):
                            break
                        self.expect("SYM", ",")
                return A.Call(t.text, args, t.pos)
            return A.ParamRef(t.text, t.pos)
        if self.accept("SYM", "("):
            e = self.expr()
            self.expect("SYM", ")")
            return e
        self.err("expected an expression")

    # --- literals -----------------------------------------------------------
    def _number(self, t: Token) -> float:
        s = t.text
        for u, f in _UNIT.items():
            if s.endswith(u) and not s.endswith("e" + u):
                return float(s[:-len(u)]) * f
        return float(s)

    def _int(self, t: Token) -> int:
        v = self._number(t)
        if v != int(v):
            self.err("expected an integer", t)
        return int(v)


def parse(src: str) -> A.Organism:
    return Parser(tokenize(src)).organism()
