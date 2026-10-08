"""Generic GA with pluggable space and fitness; surrogate screening before any hardware call."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..ledger import Ledger
from . import lineage
from .space import Space

Fitness = Callable[[dict], float]


@dataclass
class GAConfig:
    pop_size: int = 48
    generations: int = 60
    elite: int = 4
    tournament: int = 3
    mutation_rate: float = 0.12
    seed: int = 7


@dataclass
class GAResult:
    best: dict
    best_score: float
    history: List[float] = field(default_factory=list)
    population: List[dict] = field(default_factory=list)
    scores: List[float] = field(default_factory=list)


def evolve(space: Space, fitness: Fitness, cfg: GAConfig = GAConfig(), seeds: Optional[List[dict]] = None,
           ledger: Optional[Ledger] = None, run: Optional[str] = None,
           circuit_hash: Optional[Callable[[dict], str]] = None) -> GAResult:
    """With `ledger`, each generation's evaluations are appended as one lineage entry (evolve/lineage.py)
    under `run` (default: a timestamped id); `circuit_hash` (e.g. lineage.compiled_hash(space)) adds the
    compiled circuit's hash. Recording never touches the search's random stream: results are the same
    without it."""
    rng = random.Random(cfg.seed)
    run = run or time.strftime("ga-%Y%m%dT%H%M%SZ", time.gmtime())
    pop = list(seeds or [])
    origin = [("seed", [])] * len(pop)
    while len(pop) < cfg.pop_size:
        g = space.sample(rng)
        if space.screen(g) is None:
            pop.append(g)
            origin.append(("sample", []))
    scores = [fitness(g) for g in pop]

    def log(generation):
        if ledger is None:
            return
        lineage.record(ledger, run=run, generation=generation, candidates=[
            lineage.candidate(space.key(g), op, parents, score, circuit_hash(g) if circuit_hash else None)
            for g, (op, parents), score in zip(pop, origin, scores)])

    log(0)
    hist = []
    for generation in range(1, cfg.generations + 1):
        order = sorted(range(len(pop)), key=lambda i: -scores[i])
        new = [pop[i] for i in order[:cfg.elite]]
        born = [("elite", [space.key(g)]) for g in new]
        tries = 0
        while len(new) < cfg.pop_size and tries < 20 * cfg.pop_size:
            tries += 1
            a = pop[max(rng.sample(range(len(pop)), cfg.tournament), key=lambda i: scores[i])]
            b = pop[max(rng.sample(range(len(pop)), cfg.tournament), key=lambda i: scores[i])]
            c = space.mutate(space.cross(a, b, rng), rng, cfg.mutation_rate)
            if space.screen(c) is None:
                new.append(c)
                born.append(("cross+mutate", [space.key(a), space.key(b)]))
        pop, origin = new, born
        scores = [fitness(g) for g in pop]
        log(generation)
        hist.append(max(scores))
    i = max(range(len(pop)), key=lambda k: scores[k])
    return GAResult(pop[i], scores[i], hist, pop, scores)


def breed_from_ranking(space: Space, ranked_parents: List[dict], n_children: int, seen: set,
                       surrogate: Optional[Fitness] = None, rng: Optional[random.Random] = None,
                       rate: float = 0.2, oversample: int = 10, ledger: Optional[Ledger] = None,
                       run: Optional[str] = None, generation: int = 0,
                       circuit_hash: Optional[Callable[[dict], str]] = None) -> List[dict]:
    """Hardware-in-the-loop step: breed from hardware-ranked parents; screen on parity and,
    if given, rank candidates by surrogate before spending hardware. With `ledger`, each returned
    child is recorded as a "proposed" lineage candidate (no fitness yet) before any hardware is spent."""
    rng = rng or random.Random(11)
    run = run or time.strftime("hw-%Y%m%dT%H%M%SZ", time.gmtime())
    parents_of = {}
    cands: List[dict] = []
    tries = 0
    target = n_children * (oversample if surrogate else 1)
    while len(cands) < target and tries < 50 * target:
        tries += 1
        a, b = rng.sample(ranked_parents, 2) if len(ranked_parents) > 1 else (ranked_parents[0], ranked_parents[0])
        c = space.mutate(space.cross(a, b, rng), rng, rate)
        k = space.key(c)
        if k in seen or space.screen(c) is not None:
            continue
        seen.add(k); cands.append(c)
        parents_of[k] = [space.key(a), space.key(b)]
    ranked = {}
    if surrogate:   # one call per candidate, in the order sort's key would make them
        ranked = {space.key(g): surrogate(g) for g in cands}
        cands.sort(key=lambda g: -ranked[space.key(g)])
    chosen = cands[:n_children]
    if ledger is not None:
        lineage.record(ledger, run=run, generation=generation, candidates=[
            lineage.candidate(space.key(c), "proposed", parents_of[space.key(c)],
                              circuit_sha256=circuit_hash(c) if circuit_hash else None,
                              surrogate=ranked.get(space.key(c)))
            for c in chosen])
    return chosen
