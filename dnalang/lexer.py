"""Tokenizer for dnalang. Hand-written, position-tracking, no regex tricks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .ast import Pos

KEYWORDS = {
    "organism", "meta", "gene", "on", "genome", "fitness",
    "wait", "echo", "cleave", "barrier", "angle", "duration", "int",
    "dna", "metrics", "true", "false",
}

# biological spellings -> canonical IR op names (both are accepted everywhere)
GATE_ALIASES = {
    "helix": "h", "bond": "cx", "twist": "rz", "fold": "ry", "splice": "rx",
    "h": "h", "x": "x", "y": "y", "z": "z", "s": "s", "t": "t", "sx": "sx",
    "rx": "rx", "ry": "ry", "rz": "rz", "cx": "cx", "cz": "cz", "swap": "swap",
}

SYMBOLS = {"{", "}", "(", ")", "[", "]", ",", ":", ";", "@", "+", "-", "*", "/", "="}


class LexError(Exception):
    pass


@dataclass
class Token:
    kind: str       # IDENT, NUMBER, STRING, KEYWORD, SYM, ARROW, EOF
    text: str
    pos: Pos


def tokenize(src: str) -> List[Token]:
    toks: List[Token] = []
    i, line, col = 0, 1, 1
    n = len(src)

    def emit(kind: str, text: str, ln: int, c: int):
        toks.append(Token(kind, text, Pos(ln, c)))

    while i < n:
        ch = src[i]
        if ch == "\n":
            i += 1; line += 1; col = 1; continue
        if ch in " \t\r":
            i += 1; col += 1; continue
        if src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise LexError(f"{line}:{col}: unterminated block comment")
            chunk = src[i:j + 2]
            line += chunk.count("\n")
            col = (len(chunk) - chunk.rfind("\n")) if "\n" in chunk else col + len(chunk)
            i = j + 2
            continue
        if src.startswith("->", i):
            emit("ARROW", "->", line, col); i += 2; col += 2; continue
        if ch in SYMBOLS:
            emit("SYM", ch, line, col); i += 1; col += 1; continue
        if ch == '"':
            j = i + 1
            while j < n and src[j] != '"':
                if src[j] == "\n":
                    raise LexError(f"{line}:{col}: newline in string")
                j += 1
            if j >= n:
                raise LexError(f"{line}:{col}: unterminated string")
            emit("STRING", src[i + 1:j], line, col)
            col += j + 1 - i; i = j + 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and src[i + 1].isdigit()):
            j = i
            while j < n and (src[j].isdigit() or src[j] in ".eE" or (src[j] in "+-" and src[j - 1] in "eE")):
                j += 1
            # unit suffixes for durations: ns, us, ms, s
            k = j
            while k < n and src[k].isalpha():
                k += 1
            unit = src[j:k]
            if unit and unit not in ("ns", "us", "ms", "s"):
                raise LexError(f"{line}:{col}: unknown unit '{unit}'")
            emit("NUMBER", src[i:k], line, col)
            col += k - i; i = k
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            low = word.lower()
            # keywords are case-insensitive (the 2025 genomes are upper-case); identifiers are not
            emit("KEYWORD" if low in KEYWORDS else "IDENT", low if low in KEYWORDS else word, line, col)
            col += j - i; i = j
            continue
        raise LexError(f"{line}:{col}: unexpected character {ch!r}")
    emit("EOF", "", line, col)
    return toks
