"""Genome spaces. A space knows how to sample, mutate, cross, screen, and render a genome
to dnalang source. The compiler is the only path from genome to circuit."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, Sequence


class Space(Protocol):
    def sample(self, rng: random.Random) -> dict: ...
    def mutate(self, g: dict, rng: random.Random, rate: float) -> dict: ...
    def cross(self, a: dict, b: dict, rng: random.Random) -> dict: ...
    def key(self, g: dict) -> str: ...
    def to_dna(self, g: dict, **ctx) -> str: ...
    def screen(self, g: dict) -> Optional[str]: ...   # None = ok, else reason


@dataclass
class DDSpace:
    """Dynamical-decoupling sequences on a linear chain: K uniform slots, pulses in {I,X,Y}
    per sublattice (even/odd chain position), and an odd-sublattice offset in slot units.

    Baselines (none, CPMG, XY4, staggered XY4) live in the same space, so the GA and the
    textbook sequences compile through exactly the same path."""
    n_qubits: int = 8
    K: int = 8
    pulses: Sequence[str] = ("I", "X", "Y")
    offsets: Sequence[float] = (0.0, 0.25, 0.5)

    def sample(self, rng):
        return {"even": [rng.choice(self.pulses) for _ in range(self.K)],
                "odd": [rng.choice(self.pulses) for _ in range(self.K)],
                "offset": rng.choice(self.offsets)}

    def mutate(self, g, rng, rate=0.12):
        h = {"even": list(g["even"]), "odd": list(g["odd"]), "offset": g["offset"]}
        for key in ("even", "odd"):
            for k in range(self.K):
                if rng.random() < rate:
                    h[key][k] = rng.choice(self.pulses)
        if rng.random() < rate:
            h["offset"] = rng.choice(self.offsets)
        return h

    def cross(self, a, b, rng):
        return {"even": [a["even"][k] if rng.random() < 0.5 else b["even"][k] for k in range(self.K)],
                "odd": [a["odd"][k] if rng.random() < 0.5 else b["odd"][k] for k in range(self.K)],
                "offset": a["offset"] if rng.random() < 0.5 else b["offset"]}

    def key(self, g):
        return f"{''.join(g['even'])}|{''.join(g['odd'])}|{g['offset']}"

    def screen(self, g):
        for key in ("even", "odd"):
            if g[key].count("X") % 2 or g[key].count("Y") % 2:
                return f"dd-parity on {key} sublattice"
        return None

    def baselines(self) -> Dict[str, dict]:
        K = self.K
        xy = list("XYXYXYXY"[:K]) if K <= 8 else (list("XYXY") * (K // 4 + 1))[:K]
        return {
            "none": {"even": ["I"] * K, "odd": ["I"] * K, "offset": 0.0},
            "cpmg": {"even": ["X"] * K, "odd": ["X"] * K, "offset": 0.0},
            "xy4": {"even": xy, "odd": xy, "offset": 0.0},
            "xy4_stag": {"even": xy, "odd": xy, "offset": 0.5},
        }

    def to_dna(self, g, T_us: float = 16.0, name: str = "dd") -> str:
        """Render as an organism: one gene per sublattice, |+> prep, window, X-basis readout."""
        slot = T_us / self.K
        def gene(gname, seq, off):
            lines = [f"  gene {gname}() on q {{", "    helix q;"]
            t0 = 0.0
            for k, p in enumerate(seq):
                if p == "I":
                    continue
                t = (k + 0.5) * slot + off * slot
                t = min(t, T_us)
                if t - t0 > 1e-9:
                    lines.append(f"    wait({t - t0:.4f}us) q;")
                lines.append(f"    echo({p}) q;")
                t0 = t
            if T_us - t0 > 1e-9:
                lines.append(f"    wait({T_us - t0:.4f}us) q;")
            lines += ["    helix q;", "    cleave q -> c;", "  }"]
            return "\n".join(lines)
        body = [f"organism {name} {{",
                f'  meta {{ window_us: {T_us}, offset: {g["offset"]}, key: "{self.key(g)}" }}',
                gene("even_site", g["even"], 0.0),
                gene("odd_site", g["odd"], g["offset"]),
                "  genome {"]
        for q in range(self.n_qubits):
            body.append(f"    {'even_site' if q % 2 == 0 else 'odd_site'}() @ [{q}];")
        body += ["  }", "  fitness survival_plus;", "}"]
        return "\n".join(body) + "\n"
