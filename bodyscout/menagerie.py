"""Real robot arms from MuJoCo Menagerie behind the same black box as world.py.

Each arm loads its published MJCF, drops the gripper, drives the arm joints with position servos
(gravity compensated, like a real controller, so only extra payload sags) and reports one noisy
fingertip point. Channels are shuffled with a fixed seed and joint names never leave this file.

Like world.py this is hidden world: agents may use only `move`, `n_channels` and `limits`.
Get the arms with:
  git clone --depth 1 --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie.git third_party/mujoco_menagerie
  git -C third_party/mujoco_menagerie sparse-checkout set franka_emika_panda universal_robots_ur5e kinova_gen3 trossen_vx300s
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import mujoco
import numpy as np

from .world import BlackBoxRobot

ROOT = os.environ.get("MENAGERIE_PATH") or os.path.join(os.path.dirname(__file__), "..", "third_party",
                                                         "mujoco_menagerie")

# file, and the fingertip: a named end effector site, or (body, pos) for a new site
ARMS = {
    "panda": ("franka_emika_panda/panda.xml", ("hand", (0.0, 0.0, 0.1034))),  # no site: TCP between fingers
    "ur5e": ("universal_robots_ur5e/ur5e.xml", "attachment_site"),
    "gen3": ("kinova_gen3/gen3.xml", "pinch_site"),
    "vx300s": ("trossen_vx300s/vx300s.xml", "pinch"),
}
DAMAGES = ("tool", "payload", "reversed_motor", "locked_joint")
MAX_CMD = 2.0     # same channel range as world.py when every joint allows it
KP = 600.0        # servo stiffness, N m / rad


@dataclass
class MenagerieSpec:
    """Ground truth for scoring only. Hidden from every agent."""

    name: str
    joints: list                 # hidden joint names, in chain order
    perm: list                   # channel c drives joint perm[c]
    centers: list                # joint angle at command 0 (mid range), radians
    axes: list                   # world axis of each channel's joint at command 0, channel order
    zero_offsets: list           # servo misalignment per joint, radians
    signs: list = field(default_factory=list)
    locked: dict = field(default_factory=dict)
    tool: float = 0.0
    payload: float = 0.0
    family: str = "menagerie"

    @property
    def n(self) -> int:
        return len(self.joints)

    def tokens(self) -> list:
        """Structure in channel order, same tokens as world.ArmSpec: every Menagerie arm joint is a hinge."""
        return ["h" + "xyz"[int(np.argmax(np.abs(a)))] for a in self.axes]


def _compile(path, tip, tool_dir, tool, payload):
    """Load the MJCF, keep hinges only, fresh position servos, contacts off, one tip site."""
    s = mujoco.MjSpec.from_file(path)
    for j in list(s.joints):
        if j.type != mujoco.mjtJoint.mjJNT_HINGE:  # gripper fingers slide: weld them shut
            s.delete(j)
    for a in list(s.actuators):
        s.delete(a)
    for k in list(s.keys) + list(s.tendons) + list(s.equalities):  # gripper couplings go with it
        s.delete(k)
    for b in s.bodies:
        b.gravcomp = 1.0
    s.option.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONTACT
    s.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    if isinstance(tip, str):
        site = s.site(tip)
        body, pos = site.parent, np.array(site.pos, float)
        s.delete(site)
    else:
        body, pos = s.body(tip[0]), np.array(tip[1], float)
    pos = pos + tool * np.asarray(tool_dir)
    body.add_site(name="bs_tip", pos=pos, size=[0.01])
    # payload hangs on its own uncompensated body, so it sags like a real load
    load = body.add_body(name="bs_payload", pos=pos)
    load.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[0.015], mass=1e-3 + payload,
                  contype=0, conaffinity=0)
    for j in s.joints:
        s.add_actuator(target=j.name, trntype=mujoco.mjtTrn.mjTRN_JOINT).set_to_position(kp=KP, kv=0.0)
    m = s.compile()
    m.dof_damping[:] = np.maximum(m.dof_damping, 2.0 * np.sqrt(KP * np.maximum(m.dof_armature, 0.05)))
    return m


class MenagerieRobot(BlackBoxRobot):
    """A Menagerie arm as N unlabeled channels. Command c on a channel sets its joint to
    mid range + sign * c radians (+ misalignment), clipped to the joint's range; `limits`
    shrinks below +-2 when a joint's half range is smaller, so commands never saturate."""

    def __init__(self, name: str, obs_noise: float = 0.002, backlash: float = 0.01,
                 settle_steps: int = 250, seed: int = 0, shuffle: bool = True):
        file, tip = ARMS[name]
        self._path = os.path.abspath(os.path.join(ROOT, file))
        if not os.path.exists(self._path):
            raise FileNotFoundError(f"{self._path} missing: see the clone command in bodyscout/menagerie.py")
        self._tip_cfg = tip
        self.obs_noise, self.backlash, self.settle_steps = obs_noise, backlash, settle_steps
        self.rng = np.random.default_rng(seed + 991)
        self.motions = 0
        self.log = []
        m = _compile(self._path, tip, np.zeros(3), 0.0, 0.0)
        n = m.njnt
        rng = np.random.default_rng(seed + 4242)
        lo, hi = m.jnt_range[:, 0].copy(), m.jnt_range[:, 1].copy()
        unlimited = ~m.jnt_limited.astype(bool)
        lo[unlimited], hi[unlimited] = -np.pi, np.pi
        self._lo, self._hi = lo, hi
        self._cmd = float(min(MAX_CMD, ((hi - lo) / 2).min()))
        perm = rng.permutation(n) if shuffle else np.arange(n)
        spec = MenagerieSpec(name=name, joints=[m.joint(j).name for j in range(n)], perm=perm.tolist(),
                             centers=((lo + hi) / 2).tolist(), axes=[],
                             zero_offsets=rng.normal(0.0, 0.03, n).tolist(), signs=[1] * n)
        self._set_spec(spec, m)
        d = self._data
        # world axes at the home pose, and the tool direction: from the last joint out to the tip
        spec.axes = [d.xaxis[perm[c]].copy() for c in range(n)]
        tip_b = m.site_bodyid[self._tip]
        out = d.site_xpos[self._tip] - d.xanchor[n - 1]
        if np.linalg.norm(out) < 1e-6:
            out = d.xaxis[n - 1]
        self._tool_dir = d.xmat[tip_b].reshape(3, 3).T @ (out / np.linalg.norm(out))

    # ---- hidden ----------------------------------------------------------
    def _set_spec(self, spec, model=None):
        self._spec = spec
        self._model = model if model is not None else _compile(
            self._path, self._tip_cfg, self._tool_dir, spec.tool, spec.payload)
        self._data = mujoco.MjData(self._model)
        self._tip = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_SITE, "bs_tip")
        self._prev = np.zeros(spec.n)
        self._simulate(self._actual_angles(np.zeros(spec.n), noisy=False))

    def damage(self, kind: str, seed: int = 0) -> str:
        s = self._spec
        rng = np.random.default_rng(seed)
        k = int(rng.integers(1, s.n))  # never the base joint, as in world.apply_damage
        if kind == "tool":
            s.tool += 0.08
            desc = "8 cm tool attached to the hand"
        elif kind == "payload":
            s.payload += 0.35 * 5  # these arms are 10x a hobby arm; 1.75 kg is a real gripper load
            desc = "1.75 kg payload in the gripper"
        elif kind == "reversed_motor":
            s.signs[k] *= -1
            desc = f"motor {k} rewired backwards"
        elif kind == "locked_joint":
            s.locked[k] = float(rng.uniform(-0.8, 0.8))
            desc = f"joint {k} seized"
        else:
            raise ValueError(f"{kind}: Menagerie arms support {DAMAGES}")
        self._set_spec(s)
        return desc

    def _actual_angles(self, q, noisy):
        """Channel commands -> joint angles in chain order."""
        s = self._spec
        c = np.zeros(s.n)
        c[s.perm] = np.asarray(q, float)  # channel i drives joint perm[i]
        prev = np.zeros(s.n)
        prev[s.perm] = self._prev
        a = np.array(s.centers) + c * np.array(s.signs) + np.array(s.zero_offsets)
        if noisy and self.backlash > 0:
            a = a - self.backlash * np.sign(c - prev) * 0.5
        for j, ang in s.locked.items():
            a[j] = s.centers[j] + ang
        return np.clip(a, self._lo, self._hi)

    def _simulate(self, angles):
        m, d = self._model, self._data
        d.qpos[m.jnt_qposadr] = angles
        d.qvel[:] = 0
        d.ctrl[:] = angles
        for _ in range(self.settle_steps):
            mujoco.mj_step(m, d)
        mujoco.mj_kinematics(m, d)
        return d.site_xpos[self._tip].copy()

    def skeleton(self, q):
        self._simulate(self._actual_angles(np.asarray(q, float), noisy=False))
        d = self._data
        pts = [np.zeros(3)] + [d.xanchor[j].copy() for j in range(self._model.njnt)]
        return np.array(pts + [d.site_xpos[self._tip].copy()])

    # ---- public interface -------------------------------------------------
    @property
    def n_channels(self) -> int:
        return self._spec.n

    @property
    def limits(self) -> tuple[float, float]:
        return (-self._cmd, self._cmd)
