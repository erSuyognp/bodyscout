"""Smoke test for the optional dynamics stack. Skipped if jax / mujoco-mjx are not installed."""
import numpy as np
import pytest

jax = pytest.importorskip("jax")
mjx = pytest.importorskip("mujoco.mjx")

import mujoco  # noqa: E402

from bodyscout.world import build_mjcf, random_body  # noqa: E402


def test_mjx_loads_and_steps_arm():
    # Ground truth MJCF is fine here: this is a test, not an agent.
    model = mujoco.MjModel.from_xml_string(build_mjcf(random_body(1, "arm")))
    mx = mjx.put_model(model)
    dx = mjx.make_data(mx)
    dx = dx.replace(ctrl=dx.ctrl.at[:].set(0.3))
    step = jax.jit(mjx.step)
    for _ in range(20):
        dx = step(mx, dx)
    assert int(dx.time / model.opt.timestep + 0.5) == 20
    qpos = np.asarray(dx.qpos)
    assert qpos.shape == (model.nq,) and np.all(np.isfinite(qpos))
    assert np.abs(qpos).max() > 0  # the position servos actually moved the joints
