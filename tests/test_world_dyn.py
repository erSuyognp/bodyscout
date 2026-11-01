"""DynamicRobot: hidden dynamics behind a trajectory black box. Needs only mujoco (no jax)."""
import copy

import numpy as np
import pytest

from bodyscout.dynamics.world_dyn import DynArmSpec, DynamicRobot, random_dyn_spec
from bodyscout.world import FAMILIES, random_body

AGENT_API = ("n_channels", "limits", "dt", "move_trajectory")


def _step_targets(n, T=60, at=5):
    tg = np.full((T, n), -1.0)
    tg[at:] = 1.0
    return tg


def test_hidden_dynamics_drawn_in_range_and_seeded():
    a = random_dyn_spec(random_body(2, "arm"), 4)
    b = random_dyn_spec(random_body(2, "arm"), 4)
    c = random_dyn_spec(random_body(2, "arm"), 5)
    assert vars(a) == vars(b) and vars(a) != vars(c)
    assert all(0.6 <= m <= 1.6 for m in a.mass_mult)
    assert all(0.1 <= d <= 1.0 for d in a.damping)
    assert all(30 <= k <= 90 for k in a.kp)
    assert 0.0 <= a.payload <= 0.4


@pytest.mark.parametrize("family", FAMILIES)
def test_same_seed_identical_paths(family):
    body = random_body(3, family)
    rng = np.random.default_rng(0)
    tg = np.cumsum(rng.normal(0, 0.05, (80, body.n)), axis=0).clip(-2, 2)
    p1 = DynamicRobot(body, dyn_seed=7, seed=11).move_trajectory(tg)
    p2 = DynamicRobot(body, dyn_seed=7, seed=11).move_trajectory(tg)
    p3 = DynamicRobot(body, dyn_seed=8, seed=11).move_trajectory(tg)
    assert p1.shape == (80, 3)
    np.testing.assert_array_equal(p1, p2)
    assert np.abs(p1 - p3).max() > 1e-4  # different hidden dynamics, different path


@pytest.mark.parametrize("family", FAMILIES)
def test_payload_visible_in_fast_moves(family):
    ds = random_dyn_spec(random_body(1, family), 0)
    light, heavy = copy.deepcopy(ds), copy.deepcopy(ds)
    light.payload, heavy.payload = 0.0, 0.4
    tg = _step_targets(ds.n)
    a = DynamicRobot(light, obs_noise=0).true_trajectory(tg)
    b = DynamicRobot(heavy, obs_noise=0).true_trajectory(tg)
    d = np.linalg.norm(a - b, axis=1) * 1000
    assert d[5:30].max() > 10.0                 # clearly visible while moving fast
    assert d[5:30].max() > 3 * d[-1]            # much bigger than the static sag difference


def test_trajectory_budget_and_noise():
    r = DynamicRobot(random_body(1, "arm"), dyn_seed=1)
    tg = np.zeros((100, r.n_channels))
    r.move_trajectory(tg)
    assert r.motions == pytest.approx(2.0)      # T / 50
    obs = r.move_trajectory(tg)
    true = r.true_trajectory(tg)
    assert r.motions == pytest.approx(4.0)      # the scorer path is free
    assert 0.5 < np.std(obs - true) * 1000 < 4.0  # about 2 mm camera noise
    assert r.dt == 0.01
    with pytest.raises(ValueError):
        r.move_trajectory(np.zeros(r.n_channels))


def test_move_unchanged_and_starts_from_rest():
    r = DynamicRobot(random_body(1, "arm"), dyn_seed=1, obs_noise=0, backlash=0)
    q = np.array([0.3, -0.4, 0.5, 0.2, -0.1])[: r.n_channels]
    still = r.true_trajectory(np.tile(q, (30, 1)))
    assert np.abs(still - still[0]).max() < 1e-4  # at rest: holding a pose does not drift
    assert np.linalg.norm(still[0] - r.true_tip(q)) < 1e-3
    before = r.motions
    r.move(q)
    assert r.motions == before + 1


def test_dynamic_damage_kinds():
    r = DynamicRobot(random_body(1, "arm"), dyn_seed=1, obs_noise=0)
    kp0, pay0 = list(r.spec.kp), r.spec.payload
    tg = _step_targets(r.n_channels)
    before = r.true_trajectory(tg)
    # seed 1 weakens joint 2 (carries the wrist). A weak final wrist yaw barely shows (~2 mm),
    # since almost no inertia sits beyond it; that is physics, not a bug.
    r.damage("weak_motor", seed=1)
    weak = [i for i, (a, b) in enumerate(zip(kp0, r.spec.kp)) if a != b]
    assert len(weak) == 1 and weak[0] != 0
    assert r.spec.kp[weak[0]] == pytest.approx(0.5 * kp0[weak[0]])
    assert np.abs(r.true_trajectory(tg) - before).max() > 0.02
    r.damage("payload_dyn")
    assert r.spec.payload == pytest.approx(pay0 + 0.35)
    r.damage("long_link", seed=0)  # kinematic damages still work and keep the hidden dynamics
    assert isinstance(r.spec, DynArmSpec) and r.spec.payload == pytest.approx(pay0 + 0.35)


def test_agent_api_never_exposes_hidden_spec():
    r = DynamicRobot(random_body(2, "scara"), dyn_seed=3)
    hidden = r.spec
    secrets = set(hidden.mass_mult) | set(hidden.damping) | set(hidden.kp) | {hidden.payload}

    n, lim, dt = r.n_channels, r.limits, r.dt
    out = r.move_trajectory(np.zeros((10, n)))
    assert type(n) is int and type(dt) is float
    assert isinstance(lim, tuple) and all(type(v) is float for v in lim)
    # the path is a fresh float array: no view into simulator memory, no object payload
    assert isinstance(out, np.ndarray) and out.dtype == np.float64 and out.shape == (10, 3)
    assert out.base is None or not np.shares_memory(out, r._data.site_xpos)
    returned = {float(n), *map(float, lim), dt}
    assert not returned & secrets
    # hidden state lives only in underscore attributes; no public attribute holds it
    for name, val in vars(r).items():
        if not name.startswith("_"):
            assert not isinstance(val, DynArmSpec), name
            assert "mujoco" not in type(val).__module__, name
    # the agent facing names are exactly what we promise, and none of them is the spec
    for name in AGENT_API:
        assert getattr(r, name) is not hidden
