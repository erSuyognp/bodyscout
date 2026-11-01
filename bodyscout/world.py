"""The hidden world: procedurally generated jointed robots (arms, gantries, SCARA, telescoping,
two arms on one base) in MuJoCo.

Agents NEVER import anything from this file except `BlackBoxRobot.move`,
`BlackBoxRobot.n_channels`, `BlackBoxRobot.limits`, and, when a task opens or
closes the gripper, `BlackBoxRobot.grasp` and `BlackBoxRobot.ungrasp`.
Everything else (the spec, the XML, cube poses, damage, evaluation) is ground
truth used only for scoring.

`move` returns one fingertip, shape (3,), for every single-marker family. The
`twoarm` family returns both fingertips, shape (2, 3), tip 0 then tip 1.
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
    twoarm    : one shared yaw, then two limbs, each with its own fingertip (see random_twoarm)
    """
    if family == "arm":
        return random_arm(seed)
    if family == "twoarm":
        return random_twoarm(seed)
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


FAMILIES = ("arm", "gantry", "scara", "telescope")  # one fingertip. twoarm is a separate tree family.


@dataclass
class TwoArmSpec:
    """Ground truth for a shared base and two limbs. Hidden from every agent.

    Channels are in kinematic order: trunk, then limb 0, then limb 1. `limbs` lists, for each
    fingertip, the channels from the trunk out to that tip. `move` returns the tips in that order.
    """

    name: str
    pattern: list
    links: list
    tilts: list
    zero_offsets: list
    signs: list
    types: list
    link_dirs: list
    limbs: list               # channel indices, trunk first, one list per fingertip
    shoulders: list           # (x, y, z) of each limb root in the trunk frame, metres
    family: str = "twoarm"
    tool: float = 0.0
    locked: dict = field(default_factory=dict)
    payload: float = 0.0
    tip_names: tuple = ("tip0", "tip1")

    @property
    def n(self) -> int:
        return len(self.pattern)

    def tokens(self) -> list:
        """Structure in channel order, same tokens as a serial body."""
        return [t + a for t, a in zip(self.types, self.pattern)]

    def limb_tokens(self) -> list:
        """Each fingertip's chain, trunk tokens first, then that limb. Scoring only."""
        toks = self.tokens()
        return [[toks[c] for c in limb] for limb in self.limbs]


def random_twoarm(seed: int) -> TwoArmSpec:
    """Shared yaw, then two limbs that reach out horizontally so the yaw actually moves both tips.

    Limb 0 is two pitch hinges. Limb 1 is a pitch hinge and a slide along the forearm, so the two
    chains are not the same structure. Link lengths and the shoulder width vary with the seed;
    the topology does not. Channels stay in kinematic order, as the other procedural families do.
    """
    rng = np.random.default_rng(seed + 1000)
    u = lambda a, b: round(float(rng.uniform(a, b)), 3)  # noqa: E731
    types = ["h", "h", "h", "h", "s"]
    pattern = ["z", "y", "y", "y", "x"]
    links = [u(0.06, 0.10), u(0.12, 0.18), u(0.10, 0.16), u(0.12, 0.18), u(0.08, 0.14)]
    dirs = ["z", "x", "x", "x", "x"]
    n = len(types)
    y = u(0.08, 0.14)
    return TwoArmSpec(
        name=f"twoarm{seed}", pattern=pattern, links=links, types=types, link_dirs=dirs,
        tilts=rng.normal(0.0, np.deg2rad(2.0), size=(n, 2)).tolist(),
        zero_offsets=_jitter(rng, n, types=types), signs=[1] * n,
        limbs=[[0, 1, 2], [0, 3, 4]], shoulders=[(0.0, y, 0.0), (0.0, -y, 0.0)])


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


def _joint_xml(spec, i: int) -> str:
    ax = _axis(spec.pattern[i], spec.tilts[i])
    axis = f'{ax[0]:.5f} {ax[1]:.5f} {ax[2]:.5f}'
    if spec.types[i] == "h":
        return (f'<joint name="j{i}" type="hinge" axis="{axis}" '
                f'range="-2.6 2.6" damping="0.4" armature="0.01"/>')
    return (f'<joint name="j{i}" type="slide" axis="{axis}" '
            f'range="-{SLIDE_RANGE} {SLIDE_RANGE}" damping="20" armature="0.05"/>')


def _actuator_xml(spec, i: int) -> str:
    if spec.types[i] == "h":
        return f'<position joint="j{i}" kp="60" kv="1.5" ctrlrange="-2.6 2.6"/>'
    return f'<position joint="j{i}" kp="5000" kv="200" ctrlrange="-{SLIDE_RANGE} {SLIDE_RANGE}"/>'


def _build_twoarm(spec: TwoArmSpec) -> str:
    """Trunk joint first, then each limb's joints, so qpos channel i is joint i."""
    trunk = (f'<body name="b0" pos="0 0 {spec.links[0]:.4f}">{_joint_xml(spec, 0)}'
             f'<geom type="capsule" fromto="0 0 0 0 0 0.04" size="0.02" mass="0.2" rgba="0.2 0.2 0.2 1"/>')
    limbs_xml = ""
    for k, limb in enumerate(spec.limbs):
        sx, sy, sz = spec.shoulders[k]
        tip = spec.tip_names[k]
        priv = limb[1:]
        xml = f'<body name="sh{k}" pos="{sx:.4f} {sy:.4f} {sz:.4f}">'
        closing = ""
        for j, i in enumerate(priv):
            if j == 0:
                pos = "0 0 0"
            else:
                prev = priv[j - 1]
                pos = _vec(spec.link_dirs[prev], spec.links[prev])
            span = _vec(spec.link_dirs[i], spec.links[i])
            xml += (f'<body name="b{i}" pos="{pos}">{_joint_xml(spec, i)}'
                    f'<geom type="capsule" fromto="0 0 0 {span}" size="0.012" mass="0.05" rgba="0.3 0.5 0.8 1"/>')
            closing = "</body>" + closing
        last = _vec(spec.link_dirs[priv[-1]], spec.links[priv[-1]])
        xml += (f'<site name="{tip}" pos="{last}" size="0.01"/>'
                f'<geom type="sphere" pos="{last}" size="0.015" mass="0.02" rgba="0.9 0.3 0.2 1"/>')
        limbs_xml += xml + closing + "</body>"
    acts = "".join(_actuator_xml(spec, i) for i in range(spec.n))
    return (
        f'<mujoco model="{spec.name}"><compiler angle="radian"/>'
        f'<option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"><flag contact="disable"/></option>'
        f'<worldbody><light pos="0 0 2"/><geom type="plane" size="1 1 .1" rgba=".9 .9 .9 1"/>'
        f'{trunk}{limbs_xml}</body></worldbody><actuator>{acts}</actuator></mujoco>'
    )


def build_mjcf(spec: ArmSpec) -> str:
    """Nested bodies, hinge or slide joints, position servos, a fingertip site.

    A twoarm spec gets two sites, tip0 and tip1, on a shared trunk.
    """
    if getattr(spec, "family", None) == "twoarm":
        return _build_twoarm(spec)
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


@dataclass
class Cube:
    """One kinematic cube. Not a MuJoCo body, so an arm's MJCF is unchanged."""

    name: str
    pos: np.ndarray
    half: float = 0.015  # 15 mm half-size, 30 mm cube

    def __post_init__(self):
        self.pos = np.array(self.pos, float).copy()
        self.held = False


class CubeScene:
    """Cubes sitting in the workspace. Optional: a robot with no scene ignores them.

    The cubes are not in the arm MJCF and they do not move until a gripper
    command attaches one. Agents never read `cubes`; a grasp returns only a
    contact bit.
    """

    GRASP_RADIUS = 0.03  # metres, fingertip to cube centre

    def __init__(self, cubes):
        self.cubes = list(cubes)
        self.held: int | None = None
        self.grasped = False  # true once any cube has been held, including after release
        self._offset = None

    def follow(self, tip: np.ndarray) -> None:
        if self.held is None:
            return
        self.cubes[self.held].pos = np.asarray(tip, float) + self._offset

    def close(self, tip: np.ndarray) -> bool:
        """Attach the nearest free cube within GRASP_RADIUS. Hidden from agents."""
        tip = np.asarray(tip, float)
        if self.held is not None:
            return True
        best, bestd = None, self.GRASP_RADIUS
        for i, cube in enumerate(self.cubes):
            d = float(np.linalg.norm(cube.pos - tip))
            if d <= bestd:
                best, bestd = i, d
        if best is None:
            return False
        self.held = best
        self.cubes[best].held = True
        self.grasped = True
        self._offset = self.cubes[best].pos - tip
        return True

    def open(self) -> None:
        """Release the held cube where it is."""
        if self.held is None:
            return
        self.cubes[self.held].held = False
        self.held = None
        self._offset = None


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
                 settle_steps: int = 250, seed: int = 0, scene: CubeScene | None = None):
        self.obs_noise = obs_noise
        self.backlash = backlash
        self.settle_steps = settle_steps
        self.rng = np.random.default_rng(seed + 991)
        self.motions = 0
        self.log: list[tuple[np.ndarray, np.ndarray]] = []
        self._scene = scene
        self._tip_xyz = None  # last simulated fingertip, before camera noise
        self._set_spec(spec)

    def attach_scene(self, scene: CubeScene | None) -> None:
        """Scoring harness only. Does not rebuild the arm."""
        self._scene = scene

    # ---- hidden ----------------------------------------------------------
    def _set_spec(self, spec: ArmSpec) -> None:
        self._spec = spec
        self._model = mujoco.MjModel.from_xml_string(build_mjcf(spec))
        self._data = mujoco.MjData(self._model)
        self._tip_ids = None
        if getattr(spec, "family", None) == "twoarm":
            self._tip_ids = [mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_SITE, name)
                             for name in spec.tip_names]
            self._tip = self._tip_ids[0]
        else:
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
        if getattr(self, "_tip_ids", None):
            return np.stack([d.site_xpos[i].copy() for i in self._tip_ids])
        return d.site_xpos[self._tip].copy()

    def true_tip(self, q: np.ndarray) -> np.ndarray:
        """Noise free, free of charge. Only for scoring, never for agents.

        Shape (3,) for one marker, (n_tips, 3) when the body has several fingertips.
        """
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
        self._tip_xyz = tip
        scene = getattr(self, "_scene", None)  # MenagerieRobot does not call this __init__
        if scene is not None:
            scene.follow(tip if np.asarray(tip).ndim == 1 else tip[0])  # no effect unless a cube is held
        self._prev = q
        self.motions += 1
        if np.asarray(tip).ndim == 1:
            obs = tip + self.rng.normal(0.0, self.obs_noise, 3)
        else:
            obs = tip + self.rng.normal(0.0, self.obs_noise, tip.shape)
        self.log.append((q.copy(), obs.copy()))
        return obs

    def _physical_tip(self) -> np.ndarray:
        """Fingertip the gripper closes on. Internal; not an agent observation."""
        tip = getattr(self, "_tip_xyz", None)
        if tip is not None:
            return tip
        return self._simulate(self._actual_angles(self._prev, noisy=False))

    def grasp(self) -> dict:
        """Close the gripper. Returns a contact bit, never a cube pose.

        Costs one motion and does not enter the identification log.
        """
        holding = False
        scene = getattr(self, "_scene", None)
        if scene is not None:
            holding = bool(scene.close(self._physical_tip()))
        self.motions += 1
        return {"closed": True, "holding": holding}

    def ungrasp(self) -> dict:
        """Open the gripper. A held cube stays where it is."""
        scene = getattr(self, "_scene", None)
        if scene is not None:
            scene.open()
        self.motions += 1
        return {"closed": False, "holding": False}


def reachable_targets(robot: BlackBoxRobot, n: int, seed: int) -> np.ndarray:
    """Targets sampled from the true workspace, for scoring only."""
    rng = np.random.default_rng(seed + 5)
    lo, hi = robot.limits
    return np.array([robot.true_tip(rng.uniform(lo, hi, robot.n_channels)) for _ in range(n)])
