"""Hidden dynamics on top of the kinematic black box.

DynamicRobot is a BlackBoxRobot whose links, payload, joint damping and servo stiffness are drawn
from a seed and kept only in the hidden spec (DynArmSpec). Agents may use ONLY:

    n_channels, limits, dt, move_trajectory(targets)

`move()` is inherited unchanged (it runs on the same, now dynamic, body, so static poses also feel
payload sag and soft servos). Everything else here is ground truth for scoring and tests.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import mujoco
import numpy as np

from ..world import SLIDE_GAIN, SLIDE_RANGE, ArmSpec, BlackBoxRobot, build_mjcf

HINGE_KP, HINGE_DAMPING = 60.0, 0.4      # nominal values in world.build_mjcf
SLIDE_KP, SLIDE_DAMPING = 5000.0, 20.0
DT = 0.01                                 # trajectory sample period, seconds
STEPS_PER_MOTION = 50                     # T samples of a trajectory cost T / 50 motions

DYN_DAMAGES = ("payload_dyn", "weak_motor")


@dataclass
class DynArmSpec(ArmSpec):
    """ArmSpec plus hidden dynamics. Hidden from every agent.

    kp and damping are in hinge units (kp 30..90 N m/rad, damping 0.1..1.0 N m s/rad). On a slide
    joint they act as the same multiplier on the slide's nominal values (kp 5000, damping 20), so
    one seed range covers both joint types. The tip payload uses ArmSpec.payload (kg).
    """

    mass_mult: list = field(default_factory=list)   # per link capsule mass multiplier
    damping: list = field(default_factory=list)     # per joint damping
    kp: list = field(default_factory=list)          # per joint servo stiffness

    def __post_init__(self):
        super().__post_init__()
        self.mass_mult = self.mass_mult or [1.0] * self.n
        self.damping = self.damping or [HINGE_DAMPING] * self.n
        self.kp = self.kp or [HINGE_KP] * self.n


def random_dyn_spec(spec: ArmSpec, seed: int) -> DynArmSpec:
    """Attach seeded hidden dynamics to a kinematic spec (the spec itself is not modified)."""
    rng = np.random.default_rng(seed + 7000)
    n = spec.n
    base = {k: copy.deepcopy(v) for k, v in vars(spec).items()}
    base["payload"] = float(rng.uniform(0.0, 0.4))
    return DynArmSpec(**base,
                      mass_mult=rng.uniform(0.6, 1.6, n).round(3).tolist(),
                      damping=rng.uniform(0.1, 1.0, n).round(3).tolist(),
                      kp=rng.uniform(30.0, 90.0, n).round(2).tolist())


def build_dyn_model(spec: DynArmSpec) -> mujoco.MjModel:
    """Compile the kinematic MJCF, then apply hidden masses, damping and servo gains."""
    ms = mujoco.MjSpec.from_string(build_mjcf(spec))
    slide = [t == "s" for t in spec.types]
    for g in ms.geoms:  # one capsule per link body b{i}; the tip sphere already carries payload
        if g.type == mujoco.mjtGeom.mjGEOM_CAPSULE and g.parent.name.startswith("b"):
            g.mass = g.mass * spec.mass_mult[int(g.parent.name[1:])]
    for j in ms.joints:
        i = int(j.name[1:])
        j.damping[0] = spec.damping[i] * (SLIDE_DAMPING / HINGE_DAMPING if slide[i] else 1.0)
    for a in ms.actuators:
        i = int(a.target[1:])
        kp = spec.kp[i] * (SLIDE_KP / HINGE_KP if slide[i] else 1.0)
        a.gainprm[0] = kp
        a.biasprm[1] = -kp
    return ms.compile()


class DynamicRobot(BlackBoxRobot):
    """Agent facing: n_channels, limits, dt, move_trajectory. Nothing else."""

    def __init__(self, spec: ArmSpec, dyn_seed: int = 0, **kw):
        if not isinstance(spec, DynArmSpec):
            spec = random_dyn_spec(spec, dyn_seed)
        self.traj_log: list[tuple[np.ndarray, np.ndarray]] = []
        super().__init__(spec, **kw)

    # ---- hidden ----------------------------------------------------------
    def _set_spec(self, spec: DynArmSpec) -> None:
        self._spec = spec
        self._model = build_dyn_model(spec)
        self._data = mujoco.MjData(self._model)
        self._tip = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_SITE, "tip")
        self._prev = np.zeros(spec.n)
        self._substeps = int(round(DT / self._model.opt.timestep))

    def damage(self, kind: str, seed: int = 0) -> str:
        if kind not in DYN_DAMAGES:
            return super().damage(kind, seed)
        s = copy.deepcopy(self._spec)
        if kind == "payload_dyn":
            s.payload += 0.35
            desc = "350 g payload in the gripper (dynamic)"
        else:  # weak_motor; never the base joint, same convention as world.apply_damage
            k = int(np.random.default_rng(seed).integers(1, s.n))
            s.kp[k] *= 0.5
            desc = f"motor {k} lost half its stiffness"
        self._set_spec(s)
        return desc

    def _traj_angles(self, q: np.ndarray, direction: np.ndarray) -> np.ndarray:
        """Like _actual_angles, but backlash keeps the last approach direction while a joint is
        held still (sign(0) would make the gear slop vanish and reappear mid trajectory)."""
        s = self._spec
        slide = np.array([t == "s" for t in s.types])
        gain = np.where(slide, SLIDE_GAIN, 1.0)
        a = self._actual_angles(q, noisy=False)
        a = a - self.backlash * gain * direction * 0.5
        for j, ang in s.locked.items():
            a[j] = ang * gain[j]
        return np.clip(a, -np.where(slide, SLIDE_RANGE, 2.6), np.where(slide, SLIDE_RANGE, 2.6))

    def _run_trajectory(self, targets: np.ndarray, noisy: bool) -> np.ndarray:
        m, d = self._model, self._data
        direction = np.sign(targets[0] - self._prev) if noisy else np.zeros(self._spec.n)
        a0 = self._traj_angles(targets[0], direction)
        mujoco.mj_resetData(m, d)  # start from rest: settle (with sag) at targets[0]
        d.qpos[:] = a0
        d.ctrl[:] = a0
        for _ in range(self.settle_steps):
            mujoco.mj_step(m, d)
        d.qvel[:] = 0
        path = np.empty((len(targets), 3))
        prev = targets[0]
        for t, q in enumerate(targets):
            if noisy:
                step = np.sign(q - prev)
                direction = np.where(step != 0, step, direction)
            d.ctrl[:] = self._traj_angles(q, direction)
            for _ in range(self._substeps):
                mujoco.mj_step(m, d)
            path[t] = d.site_xpos[self._tip]
            prev = q
        return path

    def true_trajectory(self, targets) -> np.ndarray:
        """Noise free, free of charge. Only for scoring, never for agents."""
        return self._run_trajectory(self._check(targets), noisy=False)

    def _check(self, targets) -> np.ndarray:
        targets = np.asarray(targets, float)
        if targets.ndim != 2 or targets.shape[1] != self.n_channels or len(targets) == 0:
            raise ValueError(f"targets must be (T, {self.n_channels}), got {targets.shape}")
        return np.clip(targets, *self.limits)

    # ---- public interface -------------------------------------------------
    @property
    def dt(self) -> float:
        return DT

    def move_trajectory(self, targets) -> np.ndarray:
        """Stream joint commands at dt; returns the observed (T, 3) tip path, one sample per
        command, taken dt after it is applied. Costs T / 50 motions of budget."""
        targets = self._check(targets)
        path = self._run_trajectory(targets, noisy=True)
        self._prev = targets[-1].copy()
        self.motions += len(targets) / STEPS_PER_MOTION
        obs = path + self.rng.normal(0.0, self.obs_noise, path.shape)
        self.traj_log.append((targets.copy(), obs.copy()))
        return obs
