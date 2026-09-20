"""Local simulation via qiskit-aer. Optional noise model from a backend."""
from __future__ import annotations

from typing import Dict, List, Optional

from ..qc_ir import Circuit


def run(circuits: List[Circuit], shots: int = 1024, noise_model=None, seed: Optional[int] = None,
        dt: Optional[float] = None) -> List[Dict[str, int]]:
    from qiskit.transpiler import generate_preset_pass_manager
    from qiskit_aer import AerSimulator

    sim = AerSimulator(noise_model=noise_model)
    pm = generate_preset_pass_manager(optimization_level=0, backend=sim)
    qcs = [c.to_qiskit(dt) for c in circuits]
    # Aer needs scheduled delays in dt when a noise model has durations; without one, delays are no-ops
    res = sim.run(pm.run(qcs), shots=shots, seed_simulator=seed).result()
    return [res.get_counts(i) for i in range(len(qcs))]
