"""IBM Quantum execution with fixed layout and write-ahead ledger entries.

Token from IBM_QUANTUM_TOKEN. Layout is always caller-supplied and trivial: the
compiler never lets the transpiler choose qubits, so every condition in an
experiment shares the same physical chain.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Dict, List, Optional, Sequence

from ..ledger import Ledger
from ..qc_ir import Circuit


def service():
    from qiskit_ibm_runtime import QiskitRuntimeService
    tok = os.environ.get("IBM_QUANTUM_TOKEN")
    if not tok:
        raise RuntimeError("IBM_QUANTUM_TOKEN is not set")
    return QiskitRuntimeService(channel="ibm_quantum_platform", token=tok)


def calibration_hash(backend) -> str:
    t = backend.target
    rows = []
    for g in ("x", "sx", "cz", "ecr", "measure"):
        if g in t.operation_names:
            for qs, p in t[g].items():
                rows.append((g, list(qs), getattr(p, "error", None), getattr(p, "duration", None)))
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def transpile_fixed(circuits: List[Circuit], backend, layout: Sequence[int], optimization_level: int = 0):
    from qiskit.transpiler import generate_preset_pass_manager
    dt = backend.target.dt
    pm = generate_preset_pass_manager(optimization_level=optimization_level, backend=backend,
                                      initial_layout=list(layout), layout_method="trivial",
                                      routing_method="none", seed_transpiler=1)
    return [pm.run(c.to_qiskit(dt)) for c in circuits]


def submit(circuits: List[Circuit], backend_name: str, layout: Sequence[int], shots: int,
           ledger: Ledger, tags: Optional[Dict] = None, optimization_level: int = 0) -> str:
    from qiskit_ibm_runtime import SamplerV2
    svc = service()
    backend = svc.backend(backend_name)
    tqcs = transpile_fixed(circuits, backend, layout, optimization_level)
    twoq = [sum(1 for i in q.data if i.operation.num_qubits == 2) for q in tqcs]
    pre = ledger.append("submit-intent", {
        "backend": backend_name, "layout": list(layout), "shots": shots, "n_circuits": len(circuits),
        "circuit_hashes": [c.sha256() for c in circuits], "two_qubit_counts": twoq,
        "calibration_hash": calibration_hash(backend), "tags": tags or {},
    })
    job = SamplerV2(mode=backend).run(tqcs, shots=shots)
    ledger.append("submitted", {"intent_hash": pre["hash"], "job_id": job.job_id()})
    return job.job_id()


def fetch(job_id: str, ledger: Ledger) -> Optional[List[Dict[str, int]]]:
    svc = service()
    job = svc.job(job_id)
    if "DONE" not in str(job.status()):
        return None
    res = job.result()
    counts = [pub.data.c.get_counts() for pub in res]
    usage = None
    try:
        usage = job.usage()
    except Exception:
        pass
    ledger.append("result", {"job_id": job_id, "qpu_seconds": usage,
                             "counts_hash": hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest()})
    return counts
