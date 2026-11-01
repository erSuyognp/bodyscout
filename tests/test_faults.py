"""The pipeline condition and the fault injectors: agents stay blind, faults fire where they have a slot."""
import ast
import functools
import pathlib

import numpy as np

from bodyscout.agents import Explorer
from bodyscout.faults import PROBE_VALUES, Faults, is_probe_of
from bodyscout.world import BlackBoxRobot, random_body

ALLOWED_ROBOT_ATTRS = {"move", "n_channels", "limits"}


def test_baseline_agents_in_swarm_py_only_touch_allowed_robot_attributes():
    src = pathlib.Path(__file__).resolve().parents[1] / "bodyscout" / "swarm.py"
    classes = [n for n in ast.parse(src.read_text()).body if isinstance(n, ast.ClassDef)]
    assert {c.name for c in classes} >= {"SingleAgent", "SingleProbeAgent", "PipelineAgent"}
    used = set()
    for cls in classes:
        for node in ast.walk(cls):
            if isinstance(node, ast.Attribute):
                v = node.value
                owner = v.id if isinstance(v, ast.Name) else v.attr if isinstance(v, ast.Attribute) else ""
                if owner.endswith("robot"):
                    used.add(node.attr)
    assert used <= ALLOWED_ROBOT_ATTRS, f"baseline agents touch hidden robot attributes: {used - ALLOWED_ROBOT_ATTRS}"


def test_fault_probe_values_match_the_explorers():
    assert tuple(PROBE_VALUES) == tuple(Explorer.PROBE_VALUES)


def test_wrong_structures_are_distinct_near_misses():
    robot = BlackBoxRobot(random_body(2, "scara"), seed=2)
    truth = robot.spec.tokens()  # scoring only, read here in the test
    wrong = Faults("bad_llm", robot, seed=2).wrong_structures()
    assert len(wrong) == 3 and len({tuple(w) for w in wrong}) == 3
    for w in wrong:
        assert w != truth and sum(a != b for a, b in zip(w, truth)) == 1


def test_probe_detection():
    q = np.zeros(4)
    q[2] = 0.5
    assert is_probe_of(q, 2) and not is_probe_of(q, 1)
    assert is_probe_of(np.r_[0.8, 0.8, -1.5, 0.8], 2)
    assert not is_probe_of(np.r_[0.1, 0.3, 0.5, -0.2], 2)


@functools.lru_cache(maxsize=None)
def _run(condition, fault):
    from bodyscout.swarm import run
    robot = BlackBoxRobot(random_body(1, "scara"), seed=1)
    out = run(robot, condition, budget=40, eval_at=(40,), n_targets=4, seed=1, use_llm=False,
              unknown_body=True, faults=fault)
    out["truth"] = robot.spec.tokens()
    return out


def test_pipeline_learns_an_unknown_body_with_full_provenance():
    out = _run("pipeline", None)
    bb = out["blackboard"]
    assert out["champion"] is not None and out["champion"]["describe"]["structure"] == out["truth"]
    assert not bb.needs, "the pipeline runs a fixed schedule and posts no needs"
    assert {a.author for a in bb.artifacts if a.kind == "hypothesis"} == {"pipeline-propose"}
    ids = {a.id for a in bb.artifacts}
    for a in bb.artifacts:
        if a.kind != "source":
            assert a.parents and set(a.parents) <= ids, f"{a.kind} #{a.id} has missing parents"
    assert out["agent_cpu_s"] > 0 and out["motions"] >= 40


def test_faults_fire_only_where_a_condition_has_a_slot():
    assert _run("swarm", "wrong_finding")["fault_hits"]["wrong_finding"] == 1
    assert _run("pipeline", "wrong_finding")["fault_hits"]["wrong_finding"] == 1
    assert _run("single", "wrong_finding")["fault_hits"]["wrong_finding"] == 0
    swarm = _run("swarm", "bad_llm")
    assert swarm["fault_hits"]["bad_llm"] >= 1
    assert any(h.payload.get("fault") == "bad_llm" for h in swarm["blackboard"].of("hypothesis", epoch=-1))
    assert _run("single_probe", "bad_llm")["fault_hits"]["bad_llm"] == 0
    crash = _run("swarm", "modeler_crash")
    assert [e for e in crash["events"] if e["event"] == "fault"][0]["motion"] >= 24
    late = [m for m in crash["blackboard"].of("model", epoch=-1) if m.author == "modeler-chain"]
    assert all(m.payload["n_train"] <= 24 for m in late)
    assert _run("pipeline", "noisy_channel")["fault_hits"]["noisy_channel"] == 4


def test_no_fault_is_the_default_run():
    a, b = _run("swarm", None), _run("swarm", "none")
    assert a["curve"] == b["curve"] and a["fault_hits"] == b["fault_hits"] == {}
