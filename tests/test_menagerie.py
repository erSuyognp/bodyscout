import os

import numpy as np
import pytest

from bodyscout.menagerie import ARMS, ROOT, MenagerieRobot

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(ROOT, ARMS["ur5e"][0])),
                                reason="Menagerie not cloned (see bodyscout/menagerie.py)")


def test_menagerie_interface_matches_black_box():
    r = MenagerieRobot("panda", seed=1)
    lo, hi = r.limits
    assert r.n_channels == 7 and lo == -hi and 1.4 < hi <= 2.0  # Panda's joint 4 has a 3 rad range
    x = r.move(np.zeros(r.n_channels))
    assert x.shape == (3,) and r.motions == 1


def test_channels_are_shuffled_but_deterministic():
    a, b = MenagerieRobot("ur5e", seed=1), MenagerieRobot("ur5e", seed=1)
    assert a.spec.perm == b.spec.perm and a.spec.perm != list(range(a.n_channels))
    q = np.full(a.n_channels, 0.3)
    assert np.allclose(a.true_tip(q), b.true_tip(q))
    assert MenagerieRobot("ur5e", seed=1, shuffle=False).spec.perm == list(range(6))


@pytest.mark.parametrize("kind", ["tool", "payload"])
def test_menagerie_damage_moves_tip(kind):
    r = MenagerieRobot("ur5e", seed=2)
    q = np.full(r.n_channels, 0.4)
    before = r.true_tip(q)
    r.damage(kind)
    assert np.linalg.norm(r.true_tip(q) - before) > 0.005


def test_unsupported_damage_says_so():
    with pytest.raises(ValueError):
        MenagerieRobot("ur5e").damage("bent_axis")


def _board_with_sweeps(robot, n_mixed=16, seed=0):
    """Channel sweeps from home plus random motions, posted the way the swarm posts them."""
    from bodyscout.agents import ChannelAgent, Explorer
    from bodyscout.blackboard import Blackboard
    bb = Blackboard()
    for ch in range(robot.n_channels):
        agent = ChannelAgent(ch, robot.n_channels)
        for attempt in (0, 1):  # a joint that does not move the tip from home is swept again, bent
            for v in Explorer.PROBE_VALUES:
                q = np.full(robot.n_channels, 0.8 * attempt)
                q[ch] = v
                bb.post("observation", "t", {"q": q, "x": robot.move(q), "split": "train", "probe": ch,
                                             "attempt": attempt})
            agent.step(bb, 0)
            if agent.done:
                break
    rng = np.random.default_rng(seed)
    for q in rng.uniform(*robot.limits, (n_mixed, robot.n_channels)):
        bb.post("observation", "t", {"q": q, "x": robot.move(q), "split": "train"})
    return bb


def test_order_found_on_shuffled_arm():
    from bodyscout.agents import order_from_board
    r = MenagerieRobot("ur5e", seed=1)
    order, info = order_from_board(_board_with_sweeps(r), r.n_channels)
    assert order == list(np.argsort(r.spec.perm))  # channel driving each joint, base first
    assert info["rmse_mm"] < 15 < info["as_wired_rmse_mm"]


def test_order_keeps_wiring_when_already_in_order():
    from bodyscout.agents import order_from_board
    r = MenagerieRobot("ur5e", seed=1, shuffle=False)
    order, _ = order_from_board(_board_with_sweeps(r), r.n_channels)
    assert order == list(range(r.n_channels))


def test_chain_model_fits_in_given_order():
    from bodyscout.models import ChainModel
    r = MenagerieRobot("ur5e", seed=1)
    rng = np.random.default_rng(0)
    Q = rng.uniform(*r.limits, (60, r.n_channels))
    X = np.array([r.move(q) for q in Q])
    order = list(np.argsort(r.spec.perm))
    m = ChainModel(r.n_channels, restarts=1).fit(Q, X, patterns=[r.spec.tokens()], order=order)
    Qh = rng.uniform(*r.limits, (20, r.n_channels))
    assert m.rmse(Qh, np.array([r.true_tip(q) for q in Qh])) < 0.008
    assert m.describe()["chain_order"] == order
