"""Dynamics agents. Same rules as bodyscout/agents.py: read the board, claim needs, post artifacts
with parents, never call another agent. Robot access is limited to n_channels, limits, dt and
move_trajectory (no move, no spec, no truth).

Exciter          owns move_trajectory for learning; serves `excite` needs with fast step trajectories
DynamicsModeler  asks for excitation through a need, fits fit_dynamics on top of the current chain
                 champion, posts a `dynamics_model` artifact with its holdout path error
DynamicsMonitor  every few ticks runs one short fast sentinel trajectory; when the path error jumps
                 it refits only the payload, then only each joint's kp, and names the best cause

Dynamics changes do not start a new body epoch (the shape is unchanged, so kinematic knowledge
stays valid). Instead each dynamics anomaly starts a new "dynamics epoch": older excitation data
and models no longer describe the body and are ignored.
"""
from __future__ import annotations

import numpy as np

from ..agents import Agent, current_score
from ..blackboard import Blackboard
from .fit import fit_dynamics, path_rmse_mm

COST_DIV = 50  # a trajectory of T samples costs T / 50 motions (the robot's published price)


def dyn_epoch(bb: Blackboard) -> int:
    """How many dynamics changes have been declared in this body epoch."""
    return sum(1 for a in bb.of("anomaly") if a.payload.get("kind") == "dynamics")


def trajectories(bb: Blackboard, purpose: str, split: str | None = None):
    de = dyn_epoch(bb)
    return [a for a in bb.of("trajectory") if a.payload["purpose"] == purpose
            and a.payload["dyn_epoch"] == de and (split is None or a.payload["split"] == split)]


def chain_champion(bb: Blackboard):
    """Latest crowned chain model in this body epoch (dynamics needs a physical chain)."""
    champs = [a for a in bb.of("champion") if a.payload["family"] == "chain"]
    return champs[-1] if champs else None


def motions_seen(bb: Blackboard) -> float:
    """Budget the swarm has spent, from its own records: static motions plus trajectory costs."""
    static = sum(1 for a in bb.of("observation", epoch=-1) if not a.payload.get("carried"))
    return static + sum(a.payload["cost"] for a in bb.of("trajectory", epoch=-1))


# ---------------------------------------------------------------------------
class Exciter(Agent):
    """Serves `excite` needs: fast multi joint steps (rest, jump, jump again) that make inertia,
    stiffness and damping show up in the tip path."""

    name = "exciter"

    def __init__(self, robot, seed=0):
        self.robot = robot
        self.rng = np.random.default_rng(seed + 501)

    def design(self, T):
        n, (lo, hi) = self.robot.n_channels, self.robot.limits
        span = 0.75 * min(-lo, hi)
        tg, p = np.empty((T, n)), self.rng.uniform(-span, span, n)
        for t in range(T):
            if t in (3, T // 2):
                p = self.rng.uniform(-span, span, n)
            tg[t] = p
        return tg

    def step(self, bb, t):
        need = bb.claim("excite")
        if need is None:
            return False
        P = need.payload
        for k in range(P["train"] + P["holdout"]):
            tg = self.design(P["T"])
            path = self.robot.move_trajectory(tg)
            bb.post("trajectory", self.name, {"targets": tg, "path": path, "purpose": "excite",
                                              "split": "train" if k < P["train"] else "holdout",
                                              "dyn_epoch": P["dyn_epoch"], "cost": P["T"] / COST_DIV},
                    [need.id])
        return True


# ---------------------------------------------------------------------------
class DynamicsModeler(Agent):
    """Fits the swarm's own dynamic body on top of the kinematic champion."""

    name = "modeler-dynamics"

    def __init__(self, n, n_train=4, n_holdout=1, T=50, max_kin_mm=15.0, seed=0):
        self.n, self.n_train, self.n_holdout, self.T = n, n_train, n_holdout, T
        self.max_kin_mm, self.seed = max_kin_mm, seed
        self.requested = None   # (body epoch, dyn epoch) we already asked excitation for
        self.last_key = None

    def step(self, bb, t):
        champ = chain_champion(bb)
        if champ is None or current_score(bb, champ)["holdout_mm"] > self.max_kin_mm:
            return False  # dynamics on top of a wrong shape would fit the shape error
        bb.claim("dynamics")  # a monitor asked for a refit; the dyn epoch already moved on
        de = dyn_epoch(bb)
        train, hold = trajectories(bb, "excite", "train"), trajectories(bb, "excite", "holdout")
        if len(train) < self.n_train or len(hold) < self.n_holdout:
            if self.requested != (bb.epoch, de):
                bb.need("excite", self.name, 5.0, T=self.T, train=self.n_train - len(train),
                        holdout=self.n_holdout - len(hold), dyn_epoch=de)
                self.requested = (bb.epoch, de)
            return False
        key = (champ.id, len(train), len(hold), de)
        if key == self.last_key:
            return False
        self.last_key = key
        kin = champ.payload["_model"]
        prev = [a for a in bb.of("dynamics_model") if a.payload["dyn_epoch"] == de]
        warm = prev[-1].payload["_model"].params if prev else None
        T = lambda arts: [(a.payload["targets"], a.payload["path"]) for a in arts]  # noqa: E731
        try:
            dm = fit_dynamics(kin, T(train), init=warm)
        except Exception:
            return False
        hold_tr = T(hold)
        shape_mm = path_rmse_mm(np.array([kin.predict(tg) for tg, _ in hold_tr]),
                                np.array([p for _, p in hold_tr]))
        bb.post("dynamics_model", self.name,
                {"_model": dm, "holdout_path_mm": dm.path_rmse_mm(hold_tr), "shape_only_path_mm": shape_mm,
                 "train_path_mm": dm.fit_info["train_path_mm"], "n_traj": len(train),
                 "dyn_epoch": de, "describe": dm.describe()},
                [champ.id] + [a.id for a in train + hold])
        return True


# ---------------------------------------------------------------------------
class DynamicsMonitor(Agent):
    """Spends one short fast sentinel trajectory (T/50 motions) every `every` ticks once a
    dynamics model exists. Two jumps in a row: diagnose and declare a dynamics change."""

    name = "monitor-dynamics"

    def __init__(self, robot, every=2, T=25, k_ratio=1.5, floor_mm=2.5, seed=0):
        self.robot, self.every, self.T, self.k, self.floor = robot, every, T, k_ratio, floor_mm
        rng = np.random.default_rng(seed + 77)
        n, (lo, hi) = robot.n_channels, robot.limits
        span = 0.6 * min(-lo, hi)
        a, b = rng.uniform(-span, span, n), rng.uniform(-span, span, n)
        self.sentinel = np.tile(a, (T, 1))  # rest at a, then jump every joint to b
        self.sentinel[3:] = b
        self.base_epoch, self.baseline, self.strikes, self.alarms = None, [], [], []

    def _diagnose(self, dm, strikes):
        """Which single change explains the jump? Refit only the payload, then only each kp."""
        trajs = [(a.payload["targets"], a.payload["path"]) for a in strikes]
        fits = {"payload": fit_dynamics(dm.kin, trajs, init=dm.params, free="payload")}
        for k in range(dm.n):
            fits[f"kp{k}"] = fit_dynamics(dm.kin, trajs, init=dm.params, free=("kp", k))
        errs = {c: m.path_rmse_mm(trajs) for c, m in fits.items()}
        best = min(errs, key=errs.get)
        out = {"cause": "payload" if best == "payload" else "weak_motor",
               "refit_mm": {c: round(e, 2) for c, e in errs.items()}, "best_refit_mm": errs[best],
               "payload_added_kg": fits["payload"].params["payload"] - dm.params["payload"]}
        if best != "payload":
            k = int(best[2:])
            out.update(channel=k, kp_ratio=fits[best].params["kp"][k] / dm.params["kp"][k])
        return out

    def step(self, bb, t):
        de = dyn_epoch(bb)
        models = [a for a in bb.of("dynamics_model") if a.payload["dyn_epoch"] == de]
        if not models or t % self.every:
            return False
        art = models[-1]
        dm = art.payload["_model"]
        path = self.robot.move_trajectory(self.sentinel)
        err = path_rmse_mm(dm.predict_path(self.sentinel), path)
        obs = bb.post("trajectory", self.name, {"targets": self.sentinel.copy(), "path": path,
                                                "purpose": "sentinel", "split": "monitor", "dyn_epoch": de,
                                                "cost": self.T / COST_DIV, "surprise_mm": err}, [art.id])
        # "Normal" = the model's own holdout path error, or the best of the first two sentinels of
        # this dynamics epoch re-scored by the current model, whichever is larger. The minimum
        # (not the median) keeps one post change sentinel from inflating "normal", and models
        # refit later on old excitation data never re-learn "normal" from post change sentinels.
        # Checking starts with the first sentinel. A repeated sentinel's error is steady to about
        # 0.5 mm, so the 2.5 mm floor is roughly five times that spread.
        if (bb.epoch, de) != self.base_epoch:
            self.base_epoch, self.baseline, self.strikes = (bb.epoch, de), [], []
        if len(self.baseline) < 2:
            self.baseline.append(obs)
        base_errs = [path_rmse_mm(dm.predict_path(o.payload["targets"]), o.payload["path"]) for o in self.baseline]
        base = max(min(base_errs), art.payload["holdout_path_mm"])
        thresh = max(self.k * base, base + self.floor)
        self.strikes = self.strikes + [obs] if err > thresh else []
        if len(self.strikes) >= 2:
            diag = self._diagnose(dm, self.strikes)
            motion = motions_seen(bb)
            bb.post("anomaly", self.name, {"kind": "dynamics", "surprise_mm": err, "threshold_mm": thresh,
                                           "motion": motion, **diag},
                    [o.id for o in self.strikes] + [art.id])
            self.alarms.append(motion)
            self.strikes = []
            bb.need("dynamics", self.name, 50.0, why=f"dynamics changed: {diag['cause']}")
        return True
