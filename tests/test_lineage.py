import hashlib
import json
import random
from pathlib import Path

import pytest

from dnalang import Ledger
from dnalang.cli import main
from dnalang.evolve import lineage
from dnalang.evolve.loop import GAConfig, breed_from_ranking, evolve
from dnalang.evolve.space import DDSpace
from dnalang.evolve.surrogate import DDSurrogate

CFG = GAConfig(pop_size=8, generations=3, elite=2, seed=5)


def _ga(tmp_path, **kw):
    sp = DDSpace(n_qubits=4, K=8)
    S = DDSurrogate(4, samples=4, seed=2)
    L = Ledger(tmp_path / "runs.jsonl")
    res = evolve(sp, lambda g: S.score(g, 8, 16e-6), CFG, ledger=L, run="r1", **kw)
    return sp, S, L, res


def test_every_evaluation_is_recorded_and_the_chain_verifies(tmp_path):
    sp, _, L, res = _ga(tmp_path)
    rows = lineage.entries(L, "r1")
    assert L.verify() is None and len(rows) == CFG.pop_size * (CFG.generations + 1)
    assert sum(1 for e in L if e["kind"] == "lineage") == CFG.generations + 1    # one entry per generation
    assert {r["generation"] for r in rows} == {0, 1, 2, 3}
    assert {r["operator"] for r in rows if r["generation"] == 0} == {"sample"}
    last = [r for r in rows if r["generation"] == CFG.generations]
    assert [r["fitness"] for r in last] == pytest.approx(res.scores)
    assert sum(r["operator"] == "elite" for r in last) == CFG.elite
    keys_by_gen = {g: {r["genome"] for r in rows if r["generation"] == g} for g in range(CFG.generations + 1)}
    for r in rows:
        if r["operator"] == "cross+mutate":
            assert len(r["parents"]) == 2 and set(r["parents"]) <= keys_by_gen[r["generation"] - 1]
        if r["operator"] == "elite":
            assert r["parents"] == [r["genome"]] and r["genome"] in keys_by_gen[r["generation"] - 1]


def test_recording_does_not_change_the_search(tmp_path):
    sp, _, _, res = _ga(tmp_path)
    S = DDSurrogate(4, samples=4, seed=2)              # the surrogate is stateful: a fresh one, same seed
    plain = evolve(sp, lambda g: S.score(g, 8, 16e-6), CFG)
    assert plain.best == res.best and plain.history == res.history and plain.population == res.population


def test_trace_reaches_the_first_generation_from_the_best_genome(tmp_path):
    sp, _, L, res = _ga(tmp_path)
    path = lineage.trace(L, sp.key(res.best), "r1")
    keys = {e["genome"] for e in path}
    assert sp.key(res.best) in keys and path[0]["generation"] == 0
    assert all(e["operator"] != "elite" for e in path)
    for e in path:                      # every ancestor's own parents are in the trace too
        assert set(e["parents"]) <= keys


def test_trace_refuses_a_broken_chain_and_an_unknown_genome(tmp_path):
    sp, _, L, res = _ga(tmp_path)
    with pytest.raises(ValueError, match="no lineage entry"):
        lineage.trace(L, "not-a-genome")
    lines = L.path.read_text().splitlines()
    e = json.loads(lines[1]); e["candidates"][0]["fitness"] = 0.999
    lines[1] = json.dumps(e, sort_keys=True, separators=(",", ":"))
    L.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="does not verify"):
        lineage.trace(L, sp.key(res.best))


def test_compiled_circuit_hash_is_recorded(tmp_path):
    sp = DDSpace(n_qubits=4, K=8)
    _, _, L, res = _ga(tmp_path, circuit_hash=lineage.compiled_hash(sp, T_us=16.0))
    want = lineage.compiled_hash(sp, T_us=16.0)(res.best)
    assert any(r["genome"] == sp.key(res.best) and r["circuit_sha256"] == want for r in lineage.entries(L))


def test_hardware_proposals_are_recorded_before_any_run(tmp_path):
    sp = DDSpace(n_qubits=4, K=8)
    L = Ledger(tmp_path / "runs.jsonl")
    parents = [sp.baselines()["xy4_stag"], sp.baselines()["xy4"]]

    def score(g):                                       # deterministic, so recorded values can be checked
        return g["even"].count("X") + 0.5 * g["odd"].count("Y") + g["offset"]
    kids = breed_from_ranking(sp, parents, 3, set(), surrogate=score, rng=random.Random(1),
                              ledger=L, run="hw1", generation=4)
    same = breed_from_ranking(sp, parents, 3, set(), surrogate=score, rng=random.Random(1))
    assert kids == same                                  # recording changes nothing
    rows = lineage.entries(L, "hw1")
    assert [r["genome"] for r in rows] == [sp.key(k) for k in kids]
    assert all(r["operator"] == "proposed" and r["fitness"] is None and r["generation"] == 4 for r in rows)
    assert all(set(r["parents"]) <= {sp.key(p) for p in parents} for r in rows)
    assert [r["surrogate"] for r in rows] == pytest.approx([score(k) for k in kids])


def test_unknown_operator_and_non_finite_fitness():
    with pytest.raises(ValueError):
        lineage.candidate("g", "magic")
    assert lineage.candidate("g", "sample", fitness=float("nan"))["fitness"] is None


def test_cli_trace_lineage(tmp_path, capsys):
    sp, _, L, res = _ga(tmp_path)
    assert main(["trace-lineage", str(L.path), sp.key(res.best), "--run", "r1"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("gen   0") and any(sp.key(res.best) in line for line in out)


def test_ledger_module_is_unchanged_for_its_standalone_readers():
    """osiris-cli loads dnalang/ledger.py by file path (genome_ledger.py) and keeps a byte copy of v0.2.0
    as a test fixture; lineage lives beside it so that file stays exactly as released."""
    src = Path(__file__).resolve().parents[1] / "dnalang" / "ledger.py"
    assert hashlib.sha256(src.read_bytes()).hexdigest() == V020_LEDGER_SHA256


V020_LEDGER_SHA256 = "d2a8f371e068fc63a281e01a8e1e8893936527d4fcf9bd290f416eac0f48df20"  # dnalang/ledger.py at v0.2.0 (227261e)
