import json

from dnalang import Ledger


def test_chain_verifies_and_detects_tamper(tmp_path):
    L = Ledger(tmp_path / "runs.jsonl")
    L.append("submit-intent", {"backend": "ibm_fez", "shots": 1024})
    L.append("submitted", {"job_id": "abc"})
    L.append("result", {"job_id": "abc", "qpu_seconds": 26})
    assert L.verify() is None
    lines = (tmp_path / "runs.jsonl").read_text().splitlines()
    e = json.loads(lines[1]); e["job_id"] = "xyz"
    lines[1] = json.dumps(e, sort_keys=True, separators=(",", ":"))
    (tmp_path / "runs.jsonl").write_text("\n".join(lines) + "\n")
    assert L.verify() == "entry 1: hash mismatch"
