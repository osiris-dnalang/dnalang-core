"""Measurement-derived metrics. Every function takes count dictionaries and returns numbers.

Bitstring convention: Qiskit little-endian, i.e. counts key[-1-q] is qubit q.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np


def _n(counts: Dict[str, int]) -> int:
    return sum(counts.values())


def survival_plus(counts: Dict[str, int], qubits: Sequence[int], nq: int) -> float:
    """Mean over `qubits` of P(measured 0) — use after an H on each qubit, so 0 == |+>."""
    n = _n(counts)
    return float(np.mean([sum(v for bs, v in counts.items() if bs[nq - 1 - q] == "0") / n for q in qubits]))


def parity_expectation(counts: Dict[str, int]) -> float:
    n = _n(counts)
    return sum((1 if bs.count("1") % 2 == 0 else -1) * v for bs, v in counts.items()) / n


def ghz_fidelity(counts_z: Dict[str, int], counts_parity: List[Dict[str, int]], n: int) -> Tuple[float, float, float]:
    """F = ½(P_pop + C). counts_parity[k] is the circuit measured in the basis
    (cos φ_k X + sin φ_k Y)^{⊗n} with φ_k = 2πk/K, K = len(counts_parity) > 2n.
    C is the DFT amplitude at frequency n, so it ignores the GHZ relative phase.
    Returns (F, P_pop, C)."""
    K = len(counts_parity)
    if K <= 2 * n:
        raise ValueError(f"need > 2n parity phases, got {K} for n={n}")
    nz = _n(counts_z)
    p_pop = (counts_z.get("0" * n, 0) + counts_z.get("1" * n, 0)) / nz
    m = np.array([parity_expectation(c) for c in counts_parity])
    phis = 2 * np.pi * np.arange(K) / K
    C = 2.0 * abs(np.sum(m * np.exp(-1j * n * phis))) / K
    return 0.5 * (p_pop + C), p_pop, float(C)


def w2_marginal(a: Dict[str, int], b: Dict[str, int], nq: int) -> float:
    """Mean over qubits of the W2 distance between per-qubit Bernoulli marginals.
    For two-point distributions on {0,1}, W2 = sqrt(|p_a - p_b|)."""
    na, nb = _n(a), _n(b)
    pa = np.array([sum(v for bs, v in a.items() if bs[nq - 1 - q] == "1") / na for q in range(nq)])
    pb = np.array([sum(v for bs, v in b.items() if bs[nq - 1 - q] == "1") / nb for q in range(nq)])
    return float(np.mean(np.sqrt(np.abs(pa - pb))))


def bootstrap_ci(values: Sequence[float], n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> Tuple[float, float, float]:
    """(mean, lo, hi) percentile bootstrap over replicate values."""
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        return float(v.mean()), math.nan, math.nan
    rng = np.random.default_rng(seed)
    means = rng.choice(v, size=(n_boot, len(v)), replace=True).mean(axis=1)
    return float(v.mean()), float(np.percentile(means, 100 * alpha / 2)), float(np.percentile(means, 100 * (1 - alpha / 2)))
