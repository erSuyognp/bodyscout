"""Dynamics agents and fit_dynamics. Needs only mujoco (no jax)."""
import pathlib
import re

import numpy as np
import pytest

from bodyscout.blackboard import Blackboard
from bodyscout.dynamics.agents_dyn import DynamicsModeler, DynamicsMonitor, Exciter
from bodyscout.dynamics.fit import DynModel, fit_dynamics
from bodyscout.dynamics.world_dyn import DynamicRobot
from bodyscout.models import ChainModel
from bodyscout.world import random_body

PKG = pathlib.Path(__file__).resolve().parents[1] / "bodyscout" / "dynamics"


class AllowedOnly:
    """The robot as dynamics agents may see it. Touching anything else raises."""
    ALLOWED = ("n_channels", "limits", "dt", "move_trajectory")

    def __init__(self, robot):
        object.__setattr__(self, "_r", robot)

    def __getattr__(self, name):
        if name not in self.ALLOWED:
            raise AttributeError(f"black box rule: agents may not use robot.{name}")
        return getattr(object.__getattribute__(self, "_r"), name)


def test_agent_code_never_touches_ground_truth():
    for f in ("agents_dyn.py", "fit.py"):
        src = (PKG / f).read_text()
        assert not re.search(r"^\s*(from|import)\s+.*world", src, re.M), f
        for bad in ("robot.spec", "robot._", "true_tip", "true_trajectory", "skeleton", "build_mjcf", ".move("):
            assert bad not in src, (f, bad)


def test_payload_refit_starts_from_zero():
    """Regression: scipy's relative finite difference step vanished for a payload at 0."""
    kin = ChainModel(3, seed=0)
    kin.params, kin.types = kin.init_from_pattern(["hz", "hy", "hy"], jitter=0.0)
    truth = DynModel(kin, dict(DynModel(kin).prior(), payload=0.3))
    tg = np.full((30, 3), -0.8)
    tg[3:] = 0.9
    trajs = [(tg, truth.predict_path(tg))]
    fit = fit_dynamics(kin, trajs, init=DynModel(kin).prior(), free="payload")
    assert fit.params["payload"] == pytest.approx(0.3, abs=0.01)


@pytest.mark.parametrize("kind,expect", [("payload_dyn", "payload"), ("weak_motor", "weak_motor")])
def test_dynamics_agents_detect_and_name_cause(kind, expect):
    spec = random_body(2, "scara")
    robot = DynamicRobot(spec, dyn_seed=2, seed=2)
    rng = np.random.default_rng(0)
    # test scaffolding: a kinematic champion fitted directly (the swarm would normally post it)
    Q = rng.uniform(-2, 2, (40, robot.n_channels))
    X = np.array([robot.move(q) for q in Q])
    kin = ChainModel(robot.n_channels, restarts=2, seed=0, any_types=True).fit(Q, X, patterns=[spec.tokens()])
    bb = Blackboard()
    champ = bb.post("champion", "test", {"family": "chain", "_model": kin, "holdout_mm": 3.0, "n_holdout": 5})
    view = AllowedOnly(robot)
    agents = [Exciter(view, seed=2), DynamicsModeler(robot.n_channels, seed=2), DynamicsMonitor(view, seed=2)]
    damaged_at = None
    for t in range(60):
        n_sent = sum(a.payload["purpose"] == "sentinel" for a in bb.of("trajectory"))
        if damaged_at is None and n_sent >= 3:
            kp0 = list(robot.spec.kp)  # ground truth, read by the test only
            robot.damage(kind, seed=2)
            damaged_at = len(bb.artifacts)
        for a in agents:
            a.step(bb, t)
        if bb.of("anomaly"):
            break
    dm = bb.of("dynamics_model")[0]
    ids = {a.id for a in bb.artifacts} | {n.id for n in bb.needs}
    assert champ.id in dm.parents and all(p in ids for p in dm.parents)
    assert dm.payload["holdout_path_mm"] < dm.payload["shape_only_path_mm"] / 5
    anomalies = bb.of("anomaly")
    assert len(anomalies) == 1, "change not detected"
    an = bb.artifacts.index(anomalies[0])
    assert damaged_at is not None and an >= damaged_at, "false alarm before damage"
    p = anomalies[0].payload
    assert p["cause"] == expect
    if expect == "payload":
        assert p["payload_added_kg"] == pytest.approx(0.35, abs=0.12)
    else:
        weak = [i for i, (a, b) in enumerate(zip(kp0, robot.spec.kp)) if a != b]
        assert p["channel"] == weak[0] and p["kp_ratio"] == pytest.approx(0.5, abs=0.15)
    assert all(q in ids for q in anomalies[0].parents)


def test_make_swarm_dynamics_hook():
    from bodyscout.swarm import make_swarm
    from bodyscout.world import BlackBoxRobot
    plain = [a.name for a in make_swarm(BlackBoxRobot(random_body(1, "arm")), use_llm=False)]
    robot = DynamicRobot(random_body(1, "arm"), dyn_seed=1)
    dyn = [a.name for a in make_swarm(robot, use_llm=False, dynamics=True)]
    assert dyn[: len(plain)] == plain  # the default swarm is untouched; dynamics agents are appended
    assert dyn[len(plain):] == ["exciter", "modeler-dynamics", "monitor-dynamics"]
