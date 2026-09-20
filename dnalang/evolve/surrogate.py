"""Quasi-static surrogate for DD genomes: detuning Δ_i, nearest-neighbour ZZ J_i, pulse-amplitude
error ε_i — all constant within a shot, resampled between shots. Pure numpy statevector on
n ≤ 10 qubits. Parameters are meant to be *fitted* from hardware, not asserted."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SurrogateParams:
    sigma_delta_hz: float = 15e3
    zz_hz: float = 40e3
    zz_spread: float = 0.2
    sigma_eps: float = 0.01
    t2_us: float = 0.0            # 0 = off; else exp(-T/T2) applied to coherence
    pulse_penalty: float = 0.0


class DDSurrogate:
    def __init__(self, n_qubits: int, params: SurrogateParams = SurrogateParams(), samples: int = 24, seed: int = 0):
        self.n, self.p, self.samples = n_qubits, params, samples
        self.rng = np.random.default_rng(seed)
        N = 2 ** n_qubits
        self.basis = np.array([[(i >> (n_qubits - 1 - q)) & 1 for q in range(n_qubits)] for i in range(N)])
        self.z = 1 - 2 * self.basis
        self.zz = self.z[:, :-1] * self.z[:, 1:]
        self.flip = [np.arange(N) ^ (1 << (n_qubits - 1 - q)) for q in range(n_qubits)]
        self.yph = [np.where(self.basis[:, q] == 0, -1j, 1j) for q in range(n_qubits)]

    def _rot(self, psi, q, axis, angle):
        c, s = np.cos(angle / 2), np.sin(angle / 2)
        P = psi[self.flip[q]] if axis == "X" else self.yph[q] * psi[self.flip[q]]
        return c * psi - 1j * s * P

    def events(self, g, K, T):
        slot = T / K
        ev = []
        for k in range(K):
            for q in range(self.n):
                seq = g["even"] if q % 2 == 0 else g["odd"]
                if seq[k] == "I":
                    continue
                off = g["offset"] * slot if q % 2 else 0.0
                ev.append((min((k + 0.5) * slot + off, T), q, seq[k]))
        ev.sort()
        return ev

    def score(self, g, K: int, T_s: float) -> float:
        ev = self.events(g, K, T_s)
        plus = np.full(2 ** self.n, 2 ** (-self.n / 2), dtype=complex)
        tot = 0.0
        for _ in range(self.samples):
            delta = self.rng.normal(0, 2 * np.pi * self.p.sigma_delta_hz, self.n)
            J = 2 * np.pi * self.p.zz_hz * (1 + self.p.zz_spread * self.rng.normal(0, 1, self.n - 1))
            eps = self.rng.normal(0, self.p.sigma_eps, self.n)
            E = self.z @ delta + self.zz @ J
            psi, t0 = plus.copy(), 0.0
            for t, q, p in ev:
                psi = psi * np.exp(-1j * E * (t - t0)); t0 = t
                psi = self._rot(psi, q, p, np.pi * (1 + eps[q]))
            psi = psi * np.exp(-1j * E * (T_s - t0))
            xs = [np.real(np.vdot(psi, psi[self.flip[q]])) for q in range(self.n)]
            tot += np.mean([(1 + x) / 2 for x in xs])
        s = tot / self.samples
        if self.p.t2_us > 0:
            decay = np.exp(-(T_s * 1e6) / self.p.t2_us)
            s = 0.5 + (s - 0.5) * decay
        return s - self.p.pulse_penalty * len(ev)
