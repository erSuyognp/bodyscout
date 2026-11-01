"""Learned dynamics on top of a learned kinematic chain. Agent side: obeys the black box rule.

The swarm writes its OWN MuJoCo model from what it has learned: the ChainModel champion gives the
geometry (joint offsets, axes, tip), and fit_dynamics finds the parts that only show up when the
body moves fast: a lumped mass per link, a tip payload, and each joint's servo stiffness kp and
damping. Nothing here reads the true spec or MJCF; inputs are commanded targets and observed paths.

Scale: from positions alone, multiplying every mass, kp and damping by the same factor gives the
same motion, so a payload in kilograms is unobservable without one absolute reference. The swarm
gets that from the servo datasheet below (rotor inertia and velocity gain, the same for every robot
built from these servos). Rated kp and damping are only starting guesses; the fit moves them.
"""
from __future__ import annotations

import copy

import mujoco
import numpy as np
from mujoco import rollout
from scipy.optimize import least_squares

# servo datasheet, per joint type: rotor inertia (armature), velocity gain kv, rated kp and damping
DATASHEET = {
    "h": {"armature": 0.01, "kv": 1.5, "kp": 60.0, "damping": 0.4},      # N m/rad, N m s/rad
    "s": {"armature": 0.05, "kv": 200.0, "kp": 5000.0, "damping": 20.0},  # N/m, N s/m
}
TIMESTEP = 0.002
SETTLE_S = 0.5          # "start from rest": hold targets[0] this long before the path starts
LINK_KG_PER_M = 0.5     # prior for a light tube link; only the initial guess
R_LUMP = 0.01           # radius used to give lumped masses a small inertia


def _f(v):
    return " ".join(f"{x:.6f}" for x in v)


def path_rmse_mm(pred, path) -> float:
    """RMS 3D distance between two (T, 3) (or (K, T, 3)) tip paths, in millimetres."""
    return float(np.sqrt(np.mean(np.sum((np.asarray(pred) - np.asarray(path)) ** 2, axis=-1))) * 1000)


class DynModel:
    """A simulated copy of the body the swarm believes it has."""

    def __init__(self, kin, params: dict | None = None, dt: float = 0.01):
        self.kin, self.dt, self.n = kin, dt, kin.n
        self.types = list(kin.types)
        offs, angs, tip = kin._unpack(kin.params)
        # hinge: joint angle = command; slide: displacement = command * |axis vector| (metres)
        self.scale = np.array([1.0 if t == "h" else float(np.linalg.norm(a)) for t, a in zip(self.types, angs)])
        link_vecs = [offs[i + 1] for i in range(self.n - 1)] + [tip]
        self.link_len = np.array([float(np.linalg.norm(v)) for v in link_vecs])
        self.params = params or self.prior()
        self._build(offs, angs, tip, link_vecs)
        self.apply(self.params)

    # ---- the swarm's own MJCF -------------------------------------------------------
    def _build(self, offs, angs, tip, link_vecs):
        body, close, acts = "", "", ""
        for i in range(self.n):
            d = DATASHEET[self.types[i]]
            ax = angs[i] / (np.linalg.norm(angs[i]) + 1e-12)
            jt = "hinge" if self.types[i] == "h" else "slide"
            body += (f'<body name="b{i}" pos="{_f(offs[i])}">'
                     f'<joint name="j{i}" type="{jt}" axis="{_f(ax)}" armature="{d["armature"]}" damping="0"/>'
                     f'<geom type="sphere" size="0.004" mass="0.0001"/>'
                     f'<body name="m{i}" pos="{_f(0.5 * link_vecs[i])}">'
                     f'<geom type="sphere" size="{R_LUMP}" mass="0.05"/></body>')
            close = "</body>" + close
            acts += f'<position joint="j{i}" kp="{d["kp"]}" kv="{d["kv"]}"/>'
        body += (f'<body name="payload" pos="{_f(tip)}"><geom type="sphere" size="{R_LUMP}" mass="0.01"/></body>'
                 f'<site name="tip" pos="{_f(tip)}"/>')
        xml = (f'<mujoco><option timestep="{TIMESTEP}" gravity="0 0 -9.81" integrator="implicitfast">'
               f'<flag contact="disable"/></option><worldbody>{body}{close}</worldbody>'
               f'<actuator>{acts}</actuator><sensor><framepos objtype="site" objname="tip"/></sensor></mujoco>')
        self.xml = xml
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)
        self._mass_ids = [mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, f"m{i}") for i in range(self.n)]
        self._pay_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "payload")
        self._sub = int(round(self.dt / TIMESTEP))
        self._settle = int(round(SETTLE_S / TIMESTEP))

    def prior(self) -> dict:
        return {"mass": np.maximum(LINK_KG_PER_M * self.link_len, 0.01),
                "payload": 0.0,
                "kp": np.array([DATASHEET[t]["kp"] for t in self.types]),
                "damping": np.array([DATASHEET[t]["damping"] for t in self.types])}

    def apply(self, params: dict, model: mujoco.MjModel | None = None) -> None:
        """Write parameters into the simulator (self.model, or a copy used for finite differences)."""
        params = {k: (np.array(v, float) if np.ndim(v) else float(v)) for k, v in params.items()}
        if model is None:
            self.params, model = params, self.model
        for i, bid in enumerate(self._mass_ids):
            mi = max(float(params["mass"][i]), 1e-6)
            model.body_mass[bid] = mi
            model.body_inertia[bid] = 0.4 * mi * R_LUMP ** 2
        pay = max(params["payload"], 1e-6)
        model.body_mass[self._pay_id] = pay
        model.body_inertia[self._pay_id] = 0.4 * pay * R_LUMP ** 2
        for i in range(self.n):
            kp, kv = params["kp"][i], DATASHEET[self.types[i]]["kv"]
            model.actuator_gainprm[i, 0] = kp
            model.actuator_biasprm[i, 1:3] = (-kp, -kv)
            model.dof_damping[i] = params["damping"][i]

    # ---- simulation -----------------------------------------------------------------
    def predict_paths(self, targets_list, models=None) -> np.ndarray:
        """(K, T, n) commands, all the same T -> (K, T, 3) tip paths. `models` (optional) is a
        list of parameter-perturbed MjModels to roll out in one batch (one per K)."""
        tg = np.asarray(targets_list, float)
        if tg.ndim == 2:
            tg = tg[None]
        K, T, _ = tg.shape
        a = tg * self.scale                                      # joint space
        ctrl = np.concatenate([np.repeat(a[:, :1], self._settle, 1),
                               np.repeat(a, self._sub, 1)], axis=1)  # (K, nstep, n)
        spec = mujoco.mjtState.mjSTATE_FULLPHYSICS
        size = mujoco.mj_stateSize(self.model, spec)
        state0 = np.zeros((K, size))
        for k in range(K):
            mujoco.mj_resetData(self.model, self.data)
            self.data.qpos[:] = a[k, 0]
            mujoco.mj_getState(self.model, self.data, state0[k], spec)
        _, sens = rollout.rollout(models or self.model, self.data, state0, ctrl)
        idx = self._settle + (np.arange(T) + 1) * self._sub - 1
        return sens[:, idx, :3]

    def predict_path(self, targets) -> np.ndarray:
        return self.predict_paths(np.asarray(targets, float)[None])[0]

    def path_rmse_mm(self, trajs) -> float:
        tg, paths = _stack(trajs)
        return path_rmse_mm(self.predict_paths(tg), paths)

    def describe(self) -> dict:
        p = self.params
        return {"payload_kg": round(p["payload"], 3), "mass_kg": np.round(p["mass"], 3).tolist(),
                "kp": np.round(p["kp"], 1).tolist(), "damping": np.round(p["damping"], 3).tolist(),
                "types": self.types}


def _stack(trajs):
    tg = np.array([np.asarray(t, float) for t, _ in trajs])
    paths = np.array([np.asarray(p, float) for _, p in trajs])
    return tg, paths


# ---- parameter vector: which knobs are free ----------------------------------------
def _knobs(free, n):
    """free: 'all', 'payload', ('kp', k) or a list of those. Returns [(name, index or None)]."""
    if free == "all":
        return ([("mass", i) for i in range(n)] + [("payload", None)]
                + [("kp", i) for i in range(n)] + [("damping", i) for i in range(n)])
    if isinstance(free, str) or (isinstance(free, tuple) and len(free) == 2 and isinstance(free[1], int)):
        free = [free]
    return [(f, None) if f == "payload" else (f[0], f[1]) for f in free]


def _get(params, knob):
    name, i = knob
    return params[name] if i is None else params[name][i]


def _encode(params, knobs):
    """payload is linear (it may be 0); everything else is log space (always positive)."""
    return np.array([_get(params, k) if k[0] == "payload" else np.log(max(_get(params, k), 1e-6)) for k in knobs])


def _decode(z, base, knobs):
    p = copy.deepcopy(base)
    for v, (name, i) in zip(z, knobs):
        val = float(v) if name == "payload" else float(np.exp(v))
        if i is None:
            p[name] = val
        else:
            p[name][i] = val
    return p


def fit_dynamics(kin, trajs, dt: float = 0.01, init: dict | None = None, free="all",
                 reg: float = 2.5e-7, max_nfev: int = 40) -> DynModel:
    """Fit masses, payload, kp and damping so the swarm's own simulated body reproduces the
    observed paths. kin: a fitted ChainModel. trajs: [(targets (T, n), observed path (T, 3))].
    init: starting parameters (e.g. the previous model's). free: which knobs move (see _knobs).
    reg: weight of a pull toward the starting point (squared metres of summed path error per
    e-fold squared; keeps a full fit well posed when a knob barely matters). Returns a DynModel."""
    dm = DynModel(kin, copy.deepcopy(init) if init is not None else None, dt=dt)
    base = copy.deepcopy(dm.params)
    knobs = _knobs(free, dm.n)
    z0 = _encode(base, knobs)
    lo = np.array([0.0 if k[0] == "payload" else -np.inf for k in knobs])
    hi = np.array([2.0 if k[0] == "payload" else np.inf for k in knobs])
    lo_log = {"mass": np.log(1e-3), "kp": np.log(0.1), "damping": np.log(1e-3)}
    hi_log = {"mass": np.log(3.0), "kp": np.log(10.0), "damping": np.log(10.0)}
    for j, (name, i) in enumerate(knobs):
        if name != "payload":
            rated = 1.0 if name == "mass" else DATASHEET[dm.types[i]][name]
            lo[j], hi[j] = lo_log[name] + np.log(rated), hi_log[name] + np.log(rated)
    # start strictly inside the box: trf scales steps by distance to a bound, so a payload starting
    # at 1e-9 above 0 cannot move (1e-3 kg, or 0.1% in log space, is far enough)
    z0 = np.clip(z0, lo + 1e-3, hi - 1e-3)
    tg, paths = _stack(trajs)
    K, J = len(tg), len(knobs)
    use_reg = reg > 0 and J > 1
    R = np.sqrt(reg) * np.eye(J) if use_reg else np.zeros((0, J))
    # Finite differences with ABSOLUTE steps (scipy's relative step vanishes for a payload at 0),
    # all J perturbed bodies rolled out in one batch.
    h = np.array([5e-3 if k[0] == "payload" else 2e-3 for k in knobs])
    fd_models = [copy.copy(dm.model) for _ in range(J)]

    def residual(z):
        dm.apply(_decode(z, base, knobs))
        r = (dm.predict_paths(tg) - paths).ravel()
        return np.concatenate([r, R @ (z - z0)]) if use_reg else r

    def jac(z):
        dm.apply(_decode(z, base, knobs))
        f0 = dm.predict_paths(tg)
        steps = np.where(z + h <= hi, h, -h)
        for j in range(J):
            zj = z.copy()
            zj[j] += steps[j]
            dm.apply(_decode(zj, base, knobs), fd_models[j])
        batch = dm.predict_paths(np.tile(tg, (J, 1, 1)), models=[m for m in fd_models for _ in range(K)])
        d = (batch.reshape(J, K, *f0.shape[1:]) - f0[None]) / steps[:, None, None, None]
        Jm = d.reshape(J, -1).T
        return np.vstack([Jm, R]) if use_reg else Jm

    sol = least_squares(residual, z0, jac=jac, bounds=(lo, hi), method="trf", max_nfev=max_nfev)
    dm.apply(_decode(sol.x, base, knobs))
    dm.fit_info = {"free": [f"{n}{'' if i is None else i}" for n, i in knobs], "nfev": int(sol.nfev),
                   "train_path_mm": dm.path_rmse_mm(trajs)}
    return dm
