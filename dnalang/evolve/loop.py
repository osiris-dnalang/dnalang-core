"""Generic GA with pluggable space and fitness; surrogate screening before any hardware call."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, List, Optional

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


def evolve(space: Space, fitness: Fitness, cfg: GAConfig = GAConfig(), seeds: Optional[List[dict]] = None) -> GAResult:
    rng = random.Random(cfg.seed)
    pop = list(seeds or [])
    while len(pop) < cfg.pop_size:
        g = space.sample(rng)
        if space.screen(g) is None:
            pop.append(g)
    scores = [fitness(g) for g in pop]
    hist = []
    for _ in range(cfg.generations):
        order = sorted(range(len(pop)), key=lambda i: -scores[i])
        new = [pop[i] for i in order[:cfg.elite]]
        tries = 0
        while len(new) < cfg.pop_size and tries < 20 * cfg.pop_size:
            tries += 1
            a = pop[max(rng.sample(range(len(pop)), cfg.tournament), key=lambda i: scores[i])]
            b = pop[max(rng.sample(range(len(pop)), cfg.tournament), key=lambda i: scores[i])]
            c = space.mutate(space.cross(a, b, rng), rng, cfg.mutation_rate)
            if space.screen(c) is None:
                new.append(c)
        pop = new
        scores = [fitness(g) for g in pop]
        hist.append(max(scores))
    i = max(range(len(pop)), key=lambda k: scores[k])
    return GAResult(pop[i], scores[i], hist, pop, scores)


def breed_from_ranking(space: Space, ranked_parents: List[dict], n_children: int, seen: set,
                       surrogate: Optional[Fitness] = None, rng: Optional[random.Random] = None,
                       rate: float = 0.2, oversample: int = 10) -> List[dict]:
    """Hardware-in-the-loop step: breed from hardware-ranked parents; screen on parity and,
    if given, rank candidates by surrogate before spending hardware."""
    rng = rng or random.Random(11)
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
    if surrogate:
        cands.sort(key=lambda g: -surrogate(g))
    return cands[:n_children]
