"""Discover a jointed robot's body from motions alone, learn its dynamics, and diagnose damage (BodyScout).

Conventions: units are metres, radians, kilograms and seconds. Q (m, n) joint commands for n unlabeled channels,
X (m, 3) observed tip positions; a trajectory is (targets (T, n) commands sampled every dt seconds, path (T, 3)
observed tip positions). Nothing needs a model file or the robot type (arm, gantry, SCARA, telescoping boom):
the structure is learned. Hinge joints are tokens "h" + axis, slides "s" + axis, e.g. ["hz", "hy", "sz", "hz"].

identify_body(Q, X, structures, restarts, holdout, seed) -> dict
                                                 fit a serial chain self model to logged (command, tip) pairs; returns
                                                 structure tokens, link lengths (m), holdout tip error (mm) on a held
                                                 out share of the motions, and the fitted `model` (use predict_tip)
predict_tip(model, Q) -> np.ndarray              tip positions (m, 3) the learned body predicts for commands Q (m, n)
fit_dynamics(model, trajectories, dt) -> dict    learn link masses (kg), tip payload (kg), per joint servo stiffness kp
                                                 and damping from fast trajectories, on top of identify_body's model;
                                                 returns the parameters, train path error (mm) and the fitted `dynamics`
predict_path(dynamics, targets) -> np.ndarray    tip path (T, 3) the learned dynamics predict for commands (T, n)
diagnose_change(dynamics, trajectories) -> dict  name the single change that best explains new trajectories: payload
                                                 (with the added kg) or a weak motor (with its channel and kp ratio);
                                                 refits only the payload, then only each joint's kp, and compares
run_swarm(move, n_channels, limits, budget, seed, use_llm) -> dict
                                                 run the full BodyScout agent swarm against any robot given as a
                                                 function move(q) -> tip (3,): explorers, per channel agents,
                                                 hypothesizers, three competing self models, validators and a monitor
                                                 on a shared blackboard; returns the learned structure, holdout error,
                                                 motions spent, the fitted `model` and artifact counts
simulated_robot(family, seed) -> dict            a hidden simulated robot to try the tools on (family arm | gantry |
                                                 scara | telescope): `move`, `move_trajectory`, `dt`, `n_channels`,
                                                 `limits`, `damage(kind)` (payload_dyn | weak_motor | long_link | tool
                                                 | reversed_motor | bent_axis) and `truth()`, the hidden body, for checking

Notes: payload in kilograms needs one absolute reference, which BodyScout takes from a servo datasheet (rotor
inertia and velocity gain of the servos); see bodyscout.dynamics.fit.DATASHEET. Install with
`pip install "bodyscout @ git+https://github.com/erSuyognp/bodyscout"`; physics runs on MuJoCo (CPU).
"""
from __future__ import annotations

import numpy as np

try:  # inside ScienceClaw's scilib
    from ._pretrained import have_module
except ImportError:  # anywhere else (e.g. the BodyScout repo's own tests)
    import importlib.util

    def have_module(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False

__all__ = ["identify_body", "predict_tip", "fit_dynamics", "predict_path", "diagnose_change", "run_swarm",
           "simulated_robot"]


def available() -> bool:
    """BodyScout and MuJoCo are importable."""
    return have_module("bodyscout") and have_module("mujoco")


def _chain_summary(model) -> dict:
    d = model.describe()
    return {"structure": list(d["structure"]), "types": list(d["types"]), "axes": list(d["axes"]),
            "links_m": list(d["links_m"])}


def identify_body(Q, X, structures=None, restarts: int = 32, holdout: float = 0.2, seed: int = 0) -> dict:
    """Fit a serial chain self model to logged (command, tip) pairs.

    Q (m, n) commands, X (m, 3) tip positions in metres; at least about 6 * n motions. `structures` optionally
    lists candidate structures to try first (e.g. [["hz", "hy", "hy"]]); `restarts` random structures (hinge or
    slide, axis per channel) are also tried. With 8 restarts random logs of a SCARA, arm or telescope were often
    misidentified; 24 or more found every family tested. For a live robot, run_swarm probes each channel instead. A `holdout` share of the motions is kept out of the fit to report an honest tip error.
    Returns {structure, types, axes, links_m, train_rmse_mm, holdout_rmse_mm, n_train, n_holdout, model}."""
    from bodyscout.models import ChainModel

    Q, X = np.asarray(Q, float), np.asarray(X, float)
    if Q.ndim != 2 or X.shape != (len(Q), 3):
        raise ValueError(f"Q must be (m, n) and X (m, 3); got {Q.shape} and {X.shape}")
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(Q))
    n_hold = int(round(holdout * len(Q))) if 0 < holdout < 1 else 0
    hold, train = idx[:n_hold], idx[n_hold:]
    model = ChainModel(Q.shape[1], restarts=restarts, seed=seed, any_types=True)
    model.fit(Q[train], X[train], patterns=structures)
    out = _chain_summary(model)
    out.update(train_rmse_mm=model.rmse(Q[train], X[train]) * 1000,
               holdout_rmse_mm=model.rmse(Q[hold], X[hold]) * 1000 if n_hold else None,
               n_train=len(train), n_holdout=int(n_hold), model=model)
    return out


def predict_tip(model, Q) -> np.ndarray:
    """Tip positions (m, 3), metres, that a model from identify_body or run_swarm predicts for commands Q (m, n)."""
    return model.predict(np.atleast_2d(np.asarray(Q, float)))


def fit_dynamics(model, trajectories, dt: float = 0.01) -> dict:
    """Learn link masses, tip payload, per joint kp and damping from fast trajectories.

    `model` is the fitted chain from identify_body or run_swarm (dynamics are fitted on top of a learned shape).
    `trajectories` is a list of (targets (T, n), path (T, 3)), all with the same T, sampled every `dt` seconds,
    each starting from rest at targets[0]; fast steps (jump every joint, hold, jump again) work best.
    Returns {payload_kg, mass_kg, kp, damping, types, train_path_mm, dynamics}."""
    from bodyscout.dynamics.fit import fit_dynamics as _fit

    trajs = [(np.asarray(t, float), np.asarray(p, float)) for t, p in trajectories]
    dyn = _fit(model, trajs, dt=dt)
    d = dyn.describe()
    return {"payload_kg": d["payload_kg"], "mass_kg": d["mass_kg"], "kp": d["kp"], "damping": d["damping"],
            "types": d["types"], "train_path_mm": dyn.fit_info["train_path_mm"], "dynamics": dyn}


def predict_path(dynamics, targets) -> np.ndarray:
    """Tip path (T, 3), metres, that dynamics from fit_dynamics predict for commands targets (T, n) from rest."""
    return dynamics.predict_path(np.asarray(targets, float))


def diagnose_change(dynamics, trajectories) -> dict:
    """Name the single change that best explains new trajectories of a possibly damaged robot.

    Refits only the payload, then only each joint's kp, starting from `dynamics` (fit_dynamics' result), and
    keeps the refit with the smallest path error. Returns {cause: "payload" | "weak_motor", path_error_mm
    (before any refit), best_refit_mm, refit_mm per candidate, payload_added_kg, and channel + kp_ratio for a
    weak motor}. If path_error_mm is close to the train path error, probably nothing changed."""
    from bodyscout.dynamics.fit import diagnose_change as _diag

    trajs = [(np.asarray(t, float), np.asarray(p, float)) for t, p in trajectories]
    out = _diag(dynamics, trajs)
    out["path_error_mm"] = dynamics.path_rmse_mm(trajs)
    return out


class _CallableRobot:
    """The black box the swarm sees: n unlabeled channels in, a 3D tip out. Wraps any move(q) -> tip."""

    def __init__(self, move, n_channels: int, limits):
        self._move, self.n_channels, self.limits = move, int(n_channels), (float(limits[0]), float(limits[1]))
        self.motions = 0

    def move(self, q):
        q = np.clip(np.asarray(q, float), *self.limits)
        x = np.asarray(self._move(q), float).reshape(3)
        self.motions += 1
        return x


def run_swarm(move, n_channels: int, limits=(-2.0, 2.0), budget: int = 64, seed: int = 0, use_llm: bool = False,
              max_ticks: int = 400, goal_mm: float = 4.0) -> dict:
    """Run the full BodyScout swarm against a robot given as a function move(q) -> tip position (3,) in metres.

    q is an (n_channels,) command clipped to `limits`; every call counts as one motion of `budget`. The swarm
    does not know the robot type: per channel agents probe each channel, hypothesizers propose structures,
    three self model families compete, validators crown a champion on held out motions. Stops at the budget or
    once the champion's holdout error is under `goal_mm` with no open requests. use_llm=True adds LLM
    hypothesizers for providers whose API keys are set (runs are then not deterministic).
    Returns {structure, types, axes, links_m, holdout_mm, family, motions, model, artifacts}."""
    from bodyscout.agents import current_score
    from bodyscout.blackboard import Blackboard
    from bodyscout.swarm import make_swarm

    robot = _CallableRobot(move, n_channels, limits)
    agents = make_swarm(robot, seed, use_llm=use_llm, channels=True)
    bb, rng = Blackboard(), np.random.default_rng(seed)
    for t in range(max_ticks):
        for i in rng.permutation(len(agents)):
            agents[i].step(bb, t)
        champ = bb.latest("champion")
        quiet = not any(n.open for n in bb.needs)
        if robot.motions >= budget or (champ is not None and quiet
                                       and current_score(bb, champ)["holdout_mm"] <= goal_mm):
            break
    champ = bb.latest("champion")
    counts: dict = {}
    for a in bb.artifacts:
        counts[a.kind] = counts.get(a.kind, 0) + 1
    out = {"motions": robot.motions, "artifacts": counts, "model": None, "family": None, "holdout_mm": None,
           "structure": None, "types": None, "axes": None, "links_m": None}
    if champ is not None:
        model = champ.payload["_model"]
        out.update(model=model, family=champ.payload["family"], holdout_mm=current_score(bb, champ)["holdout_mm"])
        if champ.payload["family"] == "chain":
            out.update(_chain_summary(model))
    return out


def simulated_robot(family: str = "arm", seed: int = 1) -> dict:
    """A hidden simulated robot (MuJoCo) to try the tools on: family arm | gantry | scara | telescope.

    Returns {move(q) -> tip, move_trajectory(targets) -> path, dt, n_channels, limits, damage(kind) -> text,
    truth() -> dict}. truth() (structure tokens, link lengths, payload, kp; current, so it reflects damage) is for
    checking results only."""
    from bodyscout.dynamics.world_dyn import DynamicRobot
    from bodyscout.world import random_body

    robot = DynamicRobot(random_body(seed, family), dyn_seed=seed, seed=seed)

    def truth() -> dict:
        s = robot.spec
        return {"structure": s.tokens(), "links_m": list(s.links), "payload_kg": s.payload, "kp": list(s.kp),
                "family": s.family}

    return {"move": robot.move, "move_trajectory": robot.move_trajectory, "dt": robot.dt,
            "n_channels": robot.n_channels, "limits": robot.limits, "damage": lambda kind, seed=0: robot.damage(kind, seed),
            "truth": truth}
