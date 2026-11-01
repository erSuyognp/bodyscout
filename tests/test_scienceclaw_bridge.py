import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from bodyscout import scienceclaw_bridge as sc
from bodyscout.blackboard import Blackboard
from bodyscout.world import BlackBoxRobot, random_arm

SCIENCECLAW = Path(__file__).resolve().parents[2] / "scienceclaw"


def _board() -> Blackboard:
    """20 artifacts across kinds, two epochs, one need served, numpy payloads and a private key."""
    bb = Blackboard()
    need = bb.need("data", "validator0", 50.0, why="need holdout motions")
    probe = bb.need("probe:2", "channel2", 198.0, channel=2, attempt=1)
    rng = np.random.default_rng(0)
    obs = [bb.post("observation", f"explorer{i % 2}", {"q": rng.uniform(-2, 2, 4), "x": rng.normal(0, 0.1, 3),
                                                        "split": "train"}, [need.id]) for i in range(10)]
    f = bb.post("finding", "channel2", {"channel": 2, "type": "h", "axis": "y", "conf": 0.9},
                [o.id for o in obs[:3]] + [probe.id])
    h = bb.post("hypothesis", "hyp_findings", {"pattern": ["hz", "hy", "hy", "hx"], "rank": 0}, [f.id])
    m = bb.post("model", "modeler_chain", {"family": "chain", "_model": object(), "train_mm": 3.2},
                [h.id] + [o.id for o in obs])
    v = bb.post("verdict", "validator0", {"candidate": m.id, "family": "chain", "holdout_mm": 4.1}, [m.id])
    c = bb.post("champion", "validator0", {"candidate": m.id, "family": "chain"}, [v.id])
    bb.post("score", "validator0", {"champion": c.id, "holdout_mm": 4.1}, [c.id])
    a = bb.post("anomaly", "monitor", {"surprise_mm": 31.0, "threshold_mm": 9.0}, [c.id])
    bb.new_epoch()
    o2 = bb.post("observation", "monitor", {"q": np.zeros(4), "x": np.ones(3), "carried": True}, [a.id])
    bb.post("hypothesis", "hyp_prior", {"pattern": ["hz", "hy", "hy", "hy"], "rank": 1}, [o2.id])
    bb.post("vote", "validator1", {"champion": m.id, "basis": "holdout"}, [v.id])
    bb.need("hypotheses", "monitor", 1.0, why="body changed")
    assert len(bb.artifacts) == 20
    return bb


def test_round_trip_20_artifacts(tmp_path):
    bb = _board()
    rep = sc.export_blackboard(bb, "rt", root=tmp_path)
    assert rep["written"] == 23 and rep["skipped"] == 0  # 20 artifacts + 3 needs
    assert sc.export_blackboard(bb, "rt", root=tmp_path)["written"] == 0  # idempotent

    back = sc.import_blackboard("rt", root=tmp_path)
    assert len(back.artifacts) == 20 and len(back.needs) == 3
    for a, b in zip(bb.artifacts, back.artifacts):
        assert (a.id, a.kind, a.author, a.epoch, a.parents) == (b.id, b.kind, b.author, b.epoch, b.parents)
        assert sc._clean(a.payload) == b.payload
        assert abs(a.t - b.t) < 1e-3
    for n, m in zip(bb.needs, back.needs):
        assert (n.id, n.kind, n.author, n.pressure, n.open) == (m.id, m.kind, m.author, m.pressure, m.open)

    index = [json.loads(line) for line in (tmp_path / "artifacts" / "global_index.jsonl").read_text().splitlines()]
    by_id = {e["artifact_id"]: e for e in index}
    assert len(by_id) == 23 and all(p in by_id for e in index for p in e["parent_artifact_ids"])
    served = [e for e in index if e["fulfilled_need_parent_id"]]
    assert len(served) == 11 and all(by_id[e["fulfilled_need_parent_id"]]["needs"] for e in served)
    assert len({e["producer_agent"] for e in index}) == 9  # each of our agents is its own producer


@pytest.mark.skipif(not (SCIENCECLAW / "artifacts" / "artifact.py").exists(), reason="no ../scienceclaw checkout")
def test_scienceclaw_code_reads_our_export(tmp_path):
    def load(rel):
        spec = importlib.util.spec_from_file_location(rel.replace("/", "_"), SCIENCECLAW / rel)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod  # dataclasses look their module up here
        spec.loader.exec_module(mod)
        return mod

    artifact, pressure = load("artifacts/artifact.py"), load("artifacts/pressure.py")
    sc.export_blackboard(_board(), "rt", root=tmp_path)
    for store in (tmp_path / "artifacts").glob("BodyScout.*/store.jsonl"):
        for line in store.read_text(encoding="utf-8").splitlines():
            art = artifact.Artifact.from_dict(json.loads(line))
            assert art.content_hash == artifact.Artifact._hash_payload(art.payload)

    index = tmp_path / "artifacts" / "global_index.jsonl"
    lines = [json.loads(line) for line in index.read_text().splitlines()]
    refs = {r.query: r for _, _, r in pressure.iter_open_needs(global_index_path=index)}
    assert len(refs) == 3
    served = pressure.score_need(need=refs["robot_motion data for BodyScout self model"], global_index_lines=lines)
    unserved = pressure.score_need(need=refs["robot_motion hypotheses for BodyScout self model"],
                                   global_index_lines=lines)
    assert served < unserved  # 10 observations cover the data need, so its novelty term drops

    pytest.importorskip("pydantic")
    needs = load("artifacts/needs.py")
    for e in lines:
        for n in e["needs"]:
            needs.NeedItem(**n)


def test_robot_motion_skill_uses_only_public_interface():
    class Public:  # exposes exactly what agents may touch
        def __init__(self, r):
            self.move, self.n_channels, self.limits = r.move, r.n_channels, r.limits

    r = BlackBoxRobot(random_arm(3), seed=3)
    out = sc.robot_motion(Public(r), n=4, seed=1)
    assert out["motions"] == 4 == r.motions and len(out["results"][0]["x_mm"]) == 3
    assert sc._parse_body("probe scara7 please") == ("scara", 7)
