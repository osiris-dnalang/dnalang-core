"""Circuit lineage on the run ledger: which parents and operator produced each genome, and its fitness.

`evolve(..., ledger=L)` and `breed_from_ranking(..., ledger=L)` append one `lineage` entry per generation to the
same hash-chained `Ledger` the backends write before submitting a job. One entry per generation, not per
genome: `Ledger.append` re-reads the file to find the chain head, so per-genome entries would make a default
`GAConfig` run (48 x 61 evaluations) quadratic in time. `Ledger` itself is unchanged, so `verify()` covers
lineage entries like any other, and readers of earlier ledgers (osiris-cli's genome ledger included) see only
a new entry kind.

Entry payload (kind "lineage"):
  run          an id shared by every entry of one search
  generation   0 for the initial population; g for the population produced by breeding round g
  candidates   one dict per genome evaluated or proposed in that generation:
    genome       Space.key(genome) -- the genome's identity within its space
    operator     "seed" (supplied), "sample" (drawn from the space), "elite" (carried over unchanged),
                 "cross+mutate" (two tournament parents), "proposed" (bred from a hardware ranking, not yet run)
    parents      genome keys of the parents ([] for seed and sample, [genome] for elite)
    fitness      the score the search used for this evaluation, or null when nothing was measured yet
    circuit_sha256  (optional) the compiled circuit's canonical hash, Circuit.sha256(), when a hasher is given;
                 several genomes can compile to one circuit, which is why the genome key is kept too
    surrogate    (optional) the surrogate score a proposal was ranked by

`trace()` walks parents back to the first genomes of the run and refuses a ledger whose chain does not verify:
a lineage read from a broken chain proves nothing.
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..ledger import Ledger

KIND = "lineage"
OPERATORS = ("seed", "sample", "elite", "cross+mutate", "proposed")


def candidate(genome: str, operator: str, parents: Sequence[str] = (), fitness: Optional[float] = None,
              circuit_sha256: Optional[str] = None, surrogate: Optional[float] = None) -> Dict[str, Any]:
    if operator not in OPERATORS:
        raise ValueError(f"unknown lineage operator {operator!r}")
    c: Dict[str, Any] = {"genome": genome, "operator": operator, "parents": list(parents),
                         "fitness": _num(fitness)}
    if circuit_sha256 is not None:
        c["circuit_sha256"] = circuit_sha256
    if surrogate is not None:
        c["surrogate"] = _num(surrogate)
    return c


def _num(x: Optional[float]) -> Optional[float]:
    """JSON has no NaN or infinity; a non-finite score is recorded as null."""
    return None if x is None or not math.isfinite(float(x)) else float(x)


def record(ledger: Ledger, *, run: str, generation: int, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Append one generation's candidates (built with `candidate()`) as a single ledger entry."""
    return ledger.append(KIND, {"run": run, "generation": int(generation), "candidates": candidates})


def new_run_id(prefix: str) -> str:
    """A run id no other search will share: a timestamp alone collided for two searches in one second."""
    return time.strftime(f"{prefix}-%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]


def claim(ledger: Ledger, run: str, generation: Optional[int] = None) -> None:
    """Refuse to write into a run (or, given `generation`, a run's generation) the ledger already holds, so
    two searches can never be merged by trace()."""
    taken = {e["generation"] for e in ledger if e.get("kind") == KIND and e.get("run") == run}
    if (generation is None and taken) or generation in taken:
        where = f"run {run!r}" + ("" if generation is None else f" generation {generation}")
        raise ValueError(f"the ledger already has lineage for {where}; use a new run id")


def entries(ledger: Ledger, run: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every recorded candidate, in ledger order, each with its run and generation."""
    out = []
    for e in ledger:
        if e.get("kind") == KIND and (run is None or e.get("run") == run):
            out += [{"run": e["run"], "generation": e["generation"], **c} for c in e["candidates"]]
    return out


def trace(ledger: Ledger, genome: str, run: Optional[str] = None) -> List[Dict[str, Any]]:
    """The candidates that created `genome` and every ancestor it has in the ledger, oldest first.

    A genome is "created" by its first non-elite candidate; elites only carry a genome forward. With `run`
    unset, the latest run that contains `genome` is used. Raises ValueError if the chain is broken or
    the genome was never recorded."""
    bad = ledger.verify()
    if bad is not None:
        raise ValueError(f"ledger does not verify ({bad}); its lineage cannot be trusted")
    found = entries(ledger)
    if run is None:
        runs = [c["run"] for c in found if c["genome"] == genome]
        if not runs:
            raise ValueError(f"genome {genome!r} has no lineage entry")
        run = runs[-1]
    created: Dict[str, Dict[str, Any]] = {}
    for c in found:
        if c["run"] == run and c["operator"] != "elite":
            created.setdefault(c["genome"], c)
    if genome not in created:
        raise ValueError(f"genome {genome!r} has no lineage entry in run {run!r}")
    out, seen, todo = [], set(), [genome]
    while todo:
        key = todo.pop()
        if key in seen or key not in created:
            continue
        seen.add(key)
        out.append(created[key])
        todo.extend(created[key]["parents"])
    return sorted(out, key=lambda c: (c["generation"], c["genome"]))


def compiled_hash(space, **ctx) -> Callable[[dict], str]:
    """A hasher for `evolve(..., circuit_hash=...)`: render with Space.to_dna(**ctx), compile, hash the IR.
    Cached per genome key, since elites and repeats recompile to the same circuit."""
    from .. import lower, parse
    cache: Dict[str, str] = {}

    def h(g: dict) -> str:
        k = space.key(g)
        if k not in cache:
            cache[k] = lower(parse(space.to_dna(g, **ctx))).sha256()
        return cache[k]
    return h
