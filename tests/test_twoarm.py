"""Shared-base, two-fingertip body. Agents see only move(); the spec is read here for scoring."""
import numpy as np

from bodyscout.blackboard import Blackboard
from bodyscout.models import ChainModel
from bodyscout.world import BlackBoxRobot, random_arm, random_body


def test_twoarm_move_returns_both_tips_and_channels_split():
    robot = BlackBoxRobot(random_body(1, "twoarm"), seed=1)
    observed = robot.move(np.zeros(robot.n_channels))
    assert observed.shape == (2, 3) and robot.motions == 1
    base = robot.true_tip(np.zeros(robot.n_channels))
    assert base.shape == (2, 3) and np.linalg.norm(base[0] - base[1]) > 0.05
    for ch, affected in ((0, (True, True)), (1, (True, False)), (2, (True, False)),
                         (3, (False, True)), (4, (False, True))):
        q = np.zeros(robot.n_channels)
        q[ch] = 1.0
        moved = np.linalg.norm(robot.true_tip(q) - base, axis=1) > 0.01
        assert tuple(bool(v) for v in moved) == affected, (ch, moved)


def _sweep_channels(robot):
    from bodyscout.agents import ChannelAgent, Explorer
    bb = Blackboard()
    explorer = Explorer(robot)
    agents = [ChannelAgent(i, robot.n_channels) for i in range(robot.n_channels)]
    for t in range(16):
        for agent in agents:
            agent.step(bb, t)
        explorer.step(bb, t)
        if all(agent.done for agent in agents):
            break
    return bb


def test_channel_agents_report_which_tip_they_move():
    robot = BlackBoxRobot(random_body(1, "twoarm"), seed=1)
    bb = _sweep_channels(robot)
    by_ch = {f.payload["channel"]: f.payload for f in bb.of("finding")}
    assert [by_ch[i]["type"] for i in range(robot.n_channels)] == robot.spec.types
    assert by_ch[0]["tips"] == [0, 1]
    assert by_ch[1]["tips"] == by_ch[2]["tips"] == [0]
    assert by_ch[3]["tips"] == by_ch[4]["tips"] == [1]
    # every finding cites the sweep that produced it
    assert all(f.parents for f in bb.of("finding"))


def test_single_marker_findings_do_not_grow_a_tips_field():
    robot = BlackBoxRobot(random_body(1, "scara"), seed=1)
    bb = _sweep_channels(robot)
    assert bb.of("finding") and all("tips" not in f.payload for f in bb.of("finding"))


def test_hypothesizer_and_modeler_group_channels_into_limbs():
    from bodyscout.agents import FindingsHypothesizer, Modeler, resolve_limbs
    robot = BlackBoxRobot(random_body(2, "twoarm"), seed=2)
    bb = _sweep_channels(robot)
    rng = np.random.default_rng(0)
    for q in rng.uniform(*robot.limits, (16, robot.n_channels)):
        bb.post("observation", "extra", {"q": q, "x": robot.move(q), "split": "train"},
                [bb.of("finding")[-1].id])
    findings = {a.payload["channel"]: {**a.payload, "_id": a.id} for a in bb.of("finding")}
    assert resolve_limbs(findings, bb.of("observation"), robot.n_channels) == robot.spec.limbs
    hyp = FindingsHypothesizer(robot.n_channels)
    assert hyp.step(bb, 0)  # structures first; limb grouping is the next thing it posts
    assert hyp.step(bb, 0) and bb.latest("limbs").payload["limbs"] == robot.spec.limbs
    assert set(bb.latest("limbs").parents) == {a.id for a in bb.of("finding")}
    # the chain modeler groups the findings itself when the limbs artifact is absent
    bare = _sweep_channels(robot)
    for q in rng.uniform(*robot.limits, (16, robot.n_channels)):
        bare.post("observation", "extra", {"q": q, "x": robot.move(q), "split": "train"},
                  [bare.of("finding")[-1].id])
    modeler = Modeler("chain", robot.n_channels, seed=2, any_types=True)
    limbs, parents = modeler._limbs(bare)
    assert limbs == robot.spec.limbs and parents == []


def test_chain_tree_recovers_each_limb():
    spec = random_body(1, "twoarm")
    robot = BlackBoxRobot(spec, seed=1)
    rng = np.random.default_rng(0)
    Q = rng.uniform(-1.5, 1.5, (40, robot.n_channels))
    X = np.array([robot.move(q) for q in Q])
    model = ChainModel(robot.n_channels, restarts=1, seed=0).fit(
        Q, X, patterns=[spec.tokens()], limbs=spec.limbs)
    described = model.describe()
    assert described["limb_structure"] == spec.limb_tokens()
    assert described["limbs"] == spec.limbs
    holdout = rng.uniform(-1.5, 1.5, (15, robot.n_channels))
    truth = np.array([robot.true_tip(q) for q in holdout])
    assert model.rmse(holdout, truth) < 0.01  # under 10 mm, camera noise is 2 mm
    # a serial arm is still one marker
    arm = BlackBoxRobot(random_arm(1), seed=1)
    x = arm.move(np.zeros(arm.n_channels))
    assert x.shape == (3,)
