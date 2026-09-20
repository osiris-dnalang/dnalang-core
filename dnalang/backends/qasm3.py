"""OpenQASM 3 emission (text)."""
from __future__ import annotations

from typing import Optional

from ..qc_ir import Circuit


def emit(circ: Circuit, dt: Optional[float] = None) -> str:
    return circ.to_qasm3(dt)
