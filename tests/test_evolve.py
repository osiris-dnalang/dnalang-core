import random

from dnalang import lower, parse, check
from dnalang.evolve.space import DDSpace
from dnalang.evolve.surrogate import DDSurrogate, SurrogateParams
from dnalang.evolve.loop import GAConfig, evolve, breed_from_ranking


def test_dd_space_renders_valid_dnalang_and_screens_parity():
    sp = DDSpace(n_qubits=4, K=8)
    for name, g in sp.baselines().items():
        src = sp.to_dna(g, T_us=16.0, name=name)
        org = parse(src); d = check(org); assert d.ok(), (name, d.errors)
        assert not d.warnings, (name, d.warnings)
        circ = lower(org); assert circ.n_qubits == 4 and circ.n_cbits == 4
    bad = {"even": list("XYXYXYXI"), "odd": ["I"] * 8, "offset": 0.0}
    assert sp.screen(bad) is not None
    assert check(parse(sp.to_dna(bad))).warnings           # the compiler catches it too


def test_surrogate_prefers_staggered_under_zz():
    sp = DDSpace(n_qubits=4, K=8)
    S = DDSurrogate(4, SurrogateParams(zz_hz=40e3), samples=12, seed=1)
    b = sp.baselines()
    s = {k: S.score(g, 8, 16e-6) for k, g in b.items()}
    assert s["xy4_stag"] > s["xy4"] and s["xy4_stag"] > s["none"]


def test_ga_runs_and_never_emits_parity_violations():
    sp = DDSpace(n_qubits=4, K=8)
    S = DDSurrogate(4, samples=6, seed=2)
    res = evolve(sp, lambda g: S.score(g, 8, 16e-6), GAConfig(pop_size=12, generations=3, seed=3))
    assert all(sp.screen(g) is None for g in res.population) and res.best_score > 0.5
    kids = breed_from_ranking(sp, [res.best, sp.baselines()["xy4_stag"]], 4, set(), surrogate=lambda g: S.score(g, 8, 16e-6), rng=random.Random(1))
    assert len(kids) == 4 and all(sp.screen(g) is None for g in kids)
