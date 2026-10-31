"""The hidden world: procedurally generated jointed robots (arms, gantries, SCARA, telescoping) in MuJoCo.

Agents NEVER import anything from this file except `BlackBoxRobot.move`,
`BlackBoxRobot.n_channels` and `BlackBoxRobot.limits`. Everything else
(the spec, the XML, damage, evaluation) is ground truth used only for scoring.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import mujoco
import numpy as np

AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


@dataclass
class ArmSpec:
    """Ground truth body of one jointed robot. Hidden from every agent."""

    name: str
    pattern: list            # joint axis letters, e.g. ["z", "y", "y", "x"]
    links: list              # link lengths in metres (joint i to joint i+1, last = to tip)
    tilts: list              # small manufacturing tilt of each joint axis, (rx, ry) radians
    zero_offsets: list       # servo misalignment per joint (radians for hinges, metres for slides)
    tool: float = 0.0        # extra tool length at the tip, metres
    signs: list = field(default_factory=list)   # +1 normal, -1 motor wired backwards
    locked: dict = field(default_factory=dict)  # joint index -> stuck value
    payload: float = 0.0     # extra mass at tip, kg
    types: list = field(default_factory=list)   # "h" hinge (rotates) or "s" slide (translates)
    link_dirs: list = field(default_factory=list)  # direction each link extends: "x", "y" or "z"
    family: str = "arm"

    def __post_init__(self):
        self.types = self.types or ["h"] * self.n
        self.link_dirs = self.link_dirs or ["z"] * self.n
        self.signs = self.signs or [1] * self.n

    @property
    def n(self) -> int:
        return len(self.pattern)

    def tokens(self) -> list:
        return [t + a for t, a in zip(self.types, self.pattern)]


SLIDE_GAIN = 0.06   # metres per command unit; hidden from agents
SLIDE_RANGE = 0.15


def _jitter(rng, n, hinge_sd=0.06, slide_sd=0.004, types=None):
    types = types or ["h"] * n
    return [float(rng.normal(0, hinge_sd if t == "h" else slide_sd)) for t in types]


def random_arm(seed: int, n_joints: int | None = None) -> ArmSpec:
    """A plausible hobby arm: yaw base, then mostly pitch joints, odd wrist."""
    rng = np.random.default_rng(seed)
    n = int(n_joints or rng.integers(3, 6))
    pattern = ["z"] + [str(rng.choice(["y", "y", "y", "x", "z"])) for _ in range(n - 1)]
    links = rng.uniform(0.07, 0.20, size=n).round(3).tolist()
    tilts = rng.normal(0.0, np.deg2rad(3.0), size=(n, 2)).tolist()
    zero = rng.normal(0.0, 0.06, size=n).tolist()
    return ArmSpec(name=f"arm{seed}", pattern=pattern, links=links, tilts=tilts,
                   zero_offsets=zero, signs=[1] * n)


def random_body(seed: int, family: str) -> ArmSpec:
    """Different kinds of jointed robots, all hidden behind the same black box interface.
    arm       : rotating joints only (the original case)
    gantry    : three sliding axes x, y, z (3D printer, CNC, lab liquid handler) plus a rotating tool
    scara     : two horizontal rotating links, a vertical slide, a wrist (pick and place robots)
    telescope : yaw, pitch, an extending boom, a wrist pitch (cranes, telescoping manipulators)
    """
    if family == "arm":
        return random_arm(seed)
    rng = np.random.default_rng(seed + 1000)
    u = lambda a, b: round(float(rng.uniform(a, b)), 3)  # noqa: E731
    if family == "gantry":
        types, pattern = ["s", "s", "s", "h"], ["x", "y", "z", "z"]
        links, dirs = [u(0.03, 0.06), u(0.03, 0.06), u(0.10, 0.16), u(0.05, 0.09)], ["z", "z", "z", "x"]
    elif family == "scara":
        types, pattern = ["h", "h", "s", "h"], ["z", "z", "z", "z"]
        links, dirs = [u(0.12, 0.20), u(0.10, 0.16), u(0.06, 0.10), u(0.04, 0.07)], ["x", "x", "z", "x"]
    elif family == "telescope":
        types, pattern = ["h", "h", "s", "h"], ["z", "y", "z", "y"]
        links, dirs = [u(0.08, 0.12), u(0.12, 0.18), u(0.10, 0.15), u(0.06, 0.10)], ["z", "z", "z", "z"]
    else:
        raise ValueError(family)
    n = len(types)
    return ArmSpec(name=f"{family}{seed}", pattern=pattern, links=links,
                   tilts=rng.normal(0.0, np.deg2rad(2.0), size=(n, 2)).tolist(),
                   zero_offsets=_jitter(rng, n, types=types), types=types, link_dirs=dirs, family=family)


FAMILIES = ("arm", "gantry", "scara", "telescope")


def _axis(letter: str, tilt) -> np.ndarray:
    a = np.array(AXES[letter])
    rx, ry = tilt
    cx, sx, cy, sy = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry)
    rot_x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    rot_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    v = rot_y @ rot_x @ a
    return v / np.linalg.norm(v)


def _vec(letter: str, length: float) -> str:
    v = np.array(AXES[letter]) * length
    return f"{v[0]:.4f} {v[1]:.4f} {v[2]:.4f}"


def build_mjcf(spec: ArmSpec) -> str:
    """Nested bodies, hinge or slide joints, position servos, a fingertip site."""
    body_xml = ""
    closing = ""
    for i in range(spec.n):
        ax = _axis(spec.pattern[i], spec.tilts[i])
        pos = "0 0 0.0500" if i == 0 else _vec(spec.link_dirs[i - 1], spec.links[i - 1])
        if spec.types[i] == "h":
            joint = (f'<joint name="j{i}" type="hinge" axis="{ax[0]:.5f} {ax[1]:.5f} {ax[2]:.5f}" '
                     f'range="-2.6 2.6" damping="0.4" armature="0.01"/>')
        else:
            joint = (f'<joint name="j{i}" type="slide" axis="{ax[0]:.5f} {ax[1]:.5f} {ax[2]:.5f}" '
                     f'range="-{SLIDE_RANGE} {SLIDE_RANGE}" damping="20" armature="0.05"/>')
        body_xml += (
            f'<body name="b{i}" pos="{pos}">{joint}'
            f'<geom type="capsule" fromto="0 0 0 {_vec(spec.link_dirs[i], spec.links[i])}" size="0.012" '
            f'mass="0.05" rgba="0.3 0.5 0.8 1"/>'
        )
        closing = "</body>" + closing
    tip_v = _vec(spec.link_dirs[-1], spec.links[-1] + spec.tool)
    tip = (f'<site name="tip" pos="{tip_v}" size="0.01"/>'
           f'<geom type="sphere" pos="{tip_v}" size="0.015" '
           f'mass="{0.01 + spec.payload:.4f}" rgba="0.9 0.3 0.2 1"/>')
    acts = "".join(
        (f'<position joint="j{i}" kp="60" kv="1.5" ctrlrange="-2.6 2.6"/>' if spec.types[i] == "h" else
         f'<position joint="j{i}" kp="5000" kv="200" ctrlrange="-{SLIDE_RANGE} {SLIDE_RANGE}"/>')
        for i in range(spec.n)
    )
    return (
        f'<mujoco model="{spec.name}"><compiler angle="radian"/>'
        f'<option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"><flag contact="disable"/></option>'
        f'<worldbody><light pos="0 0 2"/><geom type="plane" size="1 1 .1" rgba=".9 .9 .9 1"/>'
        f'{body_xml}{tip}{closing}</worldbody><actuator>{acts}</actuator></mujoco>'
    )


DAMAGES = ("long_link", "tool", "reversed_motor", "locked_joint", "bent_axis", "payload")


def apply_damage(spec: ArmSpec, kind: str, rng: np.random.Generator) -> tuple[ArmSpec, str]:
    """Return a damaged copy of the spec plus a human description (hidden from agents)."""
    s = copy.deepcopy(spec)
    k = int(rng.integers(1, s.n))  # never the base joint, keeps it fair
    if kind == "long_link":
        s.links[k - 1] = round(s.links[k - 1] * 1.6, 3)
        desc = f"link {k - 1} replaced with one 60% longer"
    elif kind == "tool":
        s.tool += 0.08
        desc = "8 cm tool attached to the hand"
    elif kind == "reversed_motor":
        s.signs[k] *= -1
        desc = f"motor {k} rewired backwards"
    elif kind == "locked_joint":
        s.locked[k] = float(rng.uniform(-0.8, 0.8))
        desc = f"joint {k} seized"
    elif kind == "bent_axis":
        s.tilts[k] = [s.tilts[k][0] + np.deg2rad(25), s.tilts[k][1]]
        desc = f"joint {k} bracket bent 25 degrees"
    elif kind == "payload":
        s.payload += 0.35
        desc = "350 g payload in the gripper"
    else:
        raise ValueError(kind)
    return s, desc


class BlackBoxRobot:
    """What the agents see: N unlabeled command channels in, a noisy 3D fingertip out.

    Realism knobs: camera noise (2 mm), servo backlash, gravity sag via real
    position servos, and horn misalignment. Every `move` costs one motion of budget.
    """

    def __init__(self, spec: ArmSpec, obs_noise: float = 0.002, backlash: float = 0.01,
                 settle_steps: int = 250, seed: int = 0):
        self.obs_noise = obs_noise
        self.backlash = backlash
        self.settle_steps = settle_steps
        self.rng = np.random.default_rng(seed + 991)
        self.motions = 0
        self.log: list[tuple[np.ndarray, np.ndarray]] = []
        self._set_spec(spec)

    # ---- hidden ----------------------------------------------------------
    def _set_spec(self, spec: ArmSpec) -> None:
        self._spec = spec
        self._model = mujoco.MjModel.from_xml_string(build_mjcf(spec))
        self._data = mujoco.MjData(self._model)
        self._tip = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_SITE, "tip")
        self._prev = np.zeros(spec.n)

    def damage(self, kind: str, seed: int = 0) -> str:
        new, desc = apply_damage(self._spec, kind, np.random.default_rng(seed))
        self._set_spec(new)
        return desc

    def _actual_angles(self, q: np.ndarray, noisy: bool) -> np.ndarray:
        s = self._spec
        slide = np.array([t == "s" for t in s.types])
        gain = np.where(slide, SLIDE_GAIN, 1.0)
        a = np.asarray(q, float) * np.array(s.signs) * gain + np.array(s.zero_offsets)
        if noisy and self.backlash > 0:  # gear slop depends on approach direction
            a = a - self.backlash * gain * np.sign(q - self._prev) * 0.5
        for j, ang in s.locked.items():
            a[j] = ang * gain[j]
        lim = np.where(slide, SLIDE_RANGE, 2.6)
        return np.clip(a, -lim, lim)

    def _simulate(self, angles: np.ndarray) -> np.ndarray:
        m, d = self._model, self._data
        d.qpos[:] = angles
        d.qvel[:] = 0
        d.ctrl[:] = angles
        for _ in range(self.settle_steps):
            mujoco.mj_step(m, d)
        return d.site_xpos[self._tip].copy()

    def true_tip(self, q: np.ndarray) -> np.ndarray:
        """Noise free, free of charge. Only for scoring, never for agents."""
        return self._simulate(self._actual_angles(np.asarray(q, float), noisy=False))

    def skeleton(self, q: np.ndarray) -> np.ndarray:
        """Joint and tip positions for drawing only (visualisation, never given to agents)."""
        self._simulate(self._actual_angles(np.asarray(q, float), noisy=False))
        pts = [np.zeros(3)] + [self._data.xpos[i].copy() for i in range(1, self._model.nbody)]
        return np.array(pts + [self._data.site_xpos[self._tip].copy()])

    @property
    def spec(self) -> ArmSpec:
        return self._spec

    # ---- public interface -------------------------------------------------
    @property
    def n_channels(self) -> int:
        return self._spec.n

    @property
    def limits(self) -> tuple[float, float]:
        return (-2.0, 2.0)

    def move(self, q) -> np.ndarray:
        """Command all channels, wait for the servos to settle, observe the marker."""
        q = np.clip(np.asarray(q, float), *self.limits)
        tip = self._simulate(self._actual_angles(q, noisy=True))
        self._prev = q
        self.motions += 1
        obs = tip + self.rng.normal(0.0, self.obs_noise, 3)
        self.log.append((q.copy(), obs.copy()))
        return obs


def reachable_targets(robot: BlackBoxRobot, n: int, seed: int) -> np.ndarray:
    """Targets sampled from the true workspace, for scoring only."""
    rng = np.random.default_rng(seed + 5)
    lo, hi = robot.limits
    return np.array([robot.true_tip(rng.uniform(lo, hi, robot.n_channels)) for _ in range(n)])
