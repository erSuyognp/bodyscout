"""Cubes stay off the arm, and the task planner stays on the blackboard."""
import ast
import json
import pathlib

import numpy as np

from bodyscout.blackboard import Blackboard
from bodyscout.models import ChainModel
from bodyscout.task import TaskPlanner, evaluate_phase, score_placement
from bodyscout.world import BlackBoxRobot, Cube, CubeScene, random_arm

ALLOWED_ROBOT_ATTRS = {"move", "n_channels", "limits", "grasp", "ungrasp"}
FORBIDDEN_NAMES = {"true_tip", "skeleton", "build_mjcf", "apply_damage", "CubeScene",
                   "Explorer", "Monitor", "Validator", "Modeler"}


def _commands(robot):
    from types import SimpleNamespace
    return SimpleNamespace(move=robot.move, grasp=robot.grasp, ungrasp=robot.ungrasp,
                           n_channels=robot.n_channels, limits=robot.limits)


def _champion(bb, model, holdout_mm=2.0, parents=None):
    return bb.post("champion", "test", {"_model": model, "family": "chain", "holdout_mm": holdout_mm,
                                        "describe": {}, "candidate": None, "votes": 1}, parents or [])


class _Still:
    """Champion that always predicts the origin, so every real target is refused."""

    def predict(self, Q):
        Q = np.atleast_2d(np.asarray(Q, float))
        return np.zeros((len(Q), 3))


def test_a_scene_does_not_change_arm_observations():
    spec = random_arm(4)
    plain = BlackBoxRobot(spec, seed=4)
    with_cubes = BlackBoxRobot(spec, seed=4, scene=CubeScene([Cube("c", np.array([1.0, 1.0, 1.0]))]))
    rng = np.random.default_rng(0)
    for q in rng.uniform(-2, 2, (8, plain.n_channels)):
        assert np.array_equal(plain.move(q), with_cubes.move(q))
    assert plain.motions == with_cubes.motions
    assert "<cube" not in __import__("bodyscout.world", fromlist=["build_mjcf"]).build_mjcf(spec)


def test_grasp_carries_one_cube_and_ungrasp_leaves_it():
    robot = BlackBoxRobot(random_arm(1), seed=1)
    q_pick = np.zeros(robot.n_channels)
    q_place = np.full(robot.n_channels, 0.7)
    pick = robot.true_tip(q_pick)
    scene = CubeScene([Cube("c0", pick), Cube("c1", pick + np.array([0.3, 0.0, 0.0]))])
    other = scene.cubes[1].pos.copy()
    robot.attach_scene(scene)
    robot.move(q_pick)
    assert robot.grasp()["holding"] is True
    robot.move(q_place)
    assert np.linalg.norm(scene.cubes[0].pos - pick) > 0.02
    assert np.allclose(scene.cubes[1].pos, other)
    left = scene.cubes[0].pos.copy()
    assert robot.ungrasp()["holding"] is False
    assert scene.cubes[0].held is False
    robot.move(q_pick)
    assert np.allclose(scene.cubes[0].pos, left)
    assert np.allclose(scene.cubes[1].pos, other)


def test_grasp_misses_a_distant_cube():
    robot = BlackBoxRobot(random_arm(2), seed=2)
    q = np.zeros(robot.n_channels)
    tip = robot.true_tip(q)
    scene = CubeScene([Cube("c", tip + np.array([0.4, 0.0, 0.0]))])
    before = scene.cubes[0].pos.copy()
    robot.attach_scene(scene)
    robot.move(q)
    assert robot.grasp()["holding"] is False
    assert np.allclose(scene.cubes[0].pos, before)


def test_planner_posts_joint_targets_grasp_and_ungrasp_with_parents(tmp_path):
    spec = random_arm(1)
    teacher = BlackBoxRobot(spec, seed=1)
    rng = np.random.default_rng(0)
    Q = rng.uniform(-2, 2, (48, teacher.n_channels))
    X = np.array([teacher.move(q) for q in Q])
    model = ChainModel(teacher.n_channels, restarts=2).fit(Q, X, patterns=[spec.tokens()])
    champ = {"family": "chain", "_model": model, "holdout_mm": 2.0, "describe": model.describe(),
             "candidate": None, "votes": 1}
    rows = evaluate_phase(spec, champ, [], seed=5, n_trials=1, n_cubes=3)
    assert rows[0]["success"], rows[0]
    assert rows[0]["replan_requested"] == 0
    assert rows[0]["place_err_mm"] <= 30.0
    # provenance: the scorer's board is rebuilt inside evaluate_phase, so check a direct run
    robot = BlackBoxRobot(spec, seed=5)
    from bodyscout.task import sample_scene
    picks, places = sample_scene(robot, 1, seed=5)
    scene = CubeScene([Cube("c0", picks[0])])
    robot.attach_scene(scene)
    bb = Blackboard()
    src = bb.post("source", "test", {"source": "task"})
    _champion(bb, model, parents=[src.id])
    bb.need("task", "test", 10.0, trial=0, cube=0, pick=picks[0].tolist(), place=places[0].tolist())
    agent = TaskPlanner(_commands(robot), seed=5)
    for t in range(8):
        agent.step(bb, t)
        if agent.done:
            break
    plan = bb.latest("plan")
    assert [s["kind"] for s in plan.payload["steps"]] == ["move", "grasp", "move", "ungrasp"]
    assert plan.parents
    bb.to_jsonl(str(tmp_path / "bb.jsonl"))
    ids = {json.loads(line)["id"] for line in (tmp_path / "bb.jsonl").read_text().splitlines()}
    for art in bb.artifacts:
        if art.kind == "source":
            continue
        assert art.parents, art.kind
        assert set(art.parents) <= ids
    scored = score_placement(scene, places[0], 0, [picks[0].copy()])
    assert scored["success"], scored


def test_monitor_surprise_requests_replan_until_a_new_epoch_champion():
    robot = BlackBoxRobot(random_arm(3), seed=3)
    bb = Blackboard()
    src = bb.post("source", "test", {"source": "task"})
    model = _Still()
    _champion(bb, model, parents=[src.id])
    bb.need("task", "test", 10.0, trial=0, cube=0, pick=[0.2, 0.1, 0.3], place=[0.1, 0.2, 0.2])
    agent = TaskPlanner(_commands(robot), seed=0)
    agent.step(bb, 0)
    assert bb.latest("plan") is not None and agent.replanned is False
    alarm = bb.post("anomaly", "monitor", {"surprise_mm": 40.0, "threshold_mm": 8.0, "motion": 12},
                    [bb.latest("plan").id])
    bb.new_epoch()
    motions = robot.motions
    agent.step(bb, 1)
    assert bb.has_need("replan")
    assert bb.latest("replan").payload["source"] == "monitor"
    assert bb.latest("replan").parents[0] == alarm.id
    agent.step(bb, 2)
    assert robot.motions == motions  # still waiting; the old plan is not executed
    fresh = _champion(bb, model, parents=[alarm.id])
    agent.step(bb, 3)
    plan = bb.latest("plan")
    assert plan is not None and plan.epoch == bb.epoch
    assert alarm.id in plan.parents and fresh.id in plan.parents
    assert any(n.kind == "replan" and n.id in plan.parents for n in bb.needs)
    assert agent.replanned is True


def test_validator_surprise_requests_replan_until_a_later_champion():
    robot = BlackBoxRobot(random_arm(3), seed=4)
    bb = Blackboard()
    src = bb.post("source", "test", {"source": "task"})
    model = _Still()
    champ = _champion(bb, model, holdout_mm=2.0, parents=[src.id])
    bb.need("task", "test", 10.0, trial=1, cube=0, pick=[0.25, 0.0, 0.2], place=[-0.1, 0.15, 0.25])
    agent = TaskPlanner(_commands(robot), seed=1)
    agent.step(bb, 0)
    score = bb.post("score", "validator-0", {"champion": champ.id, "holdout_mm": 40.0, "n_holdout": 6},
                    [champ.id])
    motions = robot.motions
    agent.step(bb, 1)
    assert bb.has_need("replan")
    assert bb.latest("replan").payload["because"] == "score"
    agent.step(bb, 2)
    assert robot.motions == motions
    fresh = _champion(bb, model, holdout_mm=2.0, parents=[score.id])
    agent.step(bb, 3)
    plan = bb.latest("plan")
    assert score.id in plan.parents and fresh.id in plan.parents


def test_task_planner_source_uses_only_public_commands_and_the_board():
    src = pathlib.Path(__file__).resolve().parents[1] / "bodyscout" / "task.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TaskPlanner")
    used, names = set(), set()
    for node in ast.walk(cls):
        if isinstance(node, ast.Name):
            names.add(node.id)
        if isinstance(node, ast.Attribute):
            owner = node.value
            owner_name = owner.id if isinstance(owner, ast.Name) else owner.attr if isinstance(owner, ast.Attribute) else ""
            if owner_name.endswith("robot"):
                used.add(node.attr)
    assert used <= ALLOWED_ROBOT_ATTRS, used - ALLOWED_ROBOT_ATTRS
    assert names.isdisjoint(FORBIDDEN_NAMES)
