"""Run one condition on one robot and record the learning curve.

Conditions (same robot, same motion budget, same scorer):
  swarm   : all agents on the blackboard, no central planner
  single  : one generalist agent; random motions, one chain model, no holdout, no monitor
  mlp     : one agent; random motions, a neural network self model (the "just learn it" baseline)
"""
from __future__ import annotations

import time

import numpy as np

from .agents import ChannelAgent, Explorer, Hypothesizer, Modeler, Monitor, Validator
from .blackboard import Blackboard
from .models import ChainModel, MLPModel
from .planning import reach_errors
from .world import reachable_targets


class SingleAgent:
    """Does everything itself, in one loop. Fair: same budget, same model code."""

    def __init__(self, robot, family="chain", batch=4, seed=0, any_types=False):
        self.robot, self.family, self.batch, self.any_types = robot, family, batch, any_types
        self.rng = np.random.default_rng(seed)
        self.Q, self.X = [], []
        self.model = None
        self.seed = seed

    def step(self, t):
        lo, hi = self.robot.limits
        for q in self.rng.uniform(lo, hi, (self.batch, self.robot.n_channels)):
            self.Q.append(q)
            self.X.append(self.robot.move(q))
        Q, X = np.array(self.Q), np.array(self.X)
        if self.family == "chain" and len(Q) >= 6:
            self.model = ChainModel(self.robot.n_channels, restarts=3, seed=self.seed + t,
                                    any_types=self.any_types).fit(Q, X)
        elif self.family == "mlp" and len(Q) >= 16:
            self.model = MLPModel(self.robot.n_channels, seed=self.seed).fit(Q, X)


def make_swarm(robot, seed=0, library=None, warm=None, use_llm=None, families=("chain", "gmm", "mlp"),
               monitor=True, explore="disagreement", channels=False):
    """channels=True: the body type is unknown, so one agent per channel works out hinge or slide."""
    n = robot.n_channels
    agents = [Hypothesizer(n, library=library, use_llm=use_llm, wait_for_channels=channels),
              Explorer(robot, mode=explore, seed=seed),
              *[Modeler(f, n, seed=seed, warm=warm if f == "chain" else None, any_types=channels)
                for f in families],
              Validator(n, seed=seed)]
    if channels:
        agents += [ChannelAgent(i, n) for i in range(n)]
    if monitor:
        agents.append(Monitor(robot, seed=seed))
    return agents


def run(robot, condition="swarm", budget=64, eval_at=(8, 12, 16, 24, 32, 48, 64), n_targets=12,
        seed=0, damage=None, library=None, warm=None, use_llm=None, max_ticks=400, verbose=False,
        on_tick=None, unknown_body=False):
    """damage = (motion_count, kind). Returns dict with curve [(motions, median_reach_mm)], blackboard."""
    rng = np.random.default_rng(seed)
    targets = reachable_targets(robot, n_targets, seed)
    bb = Blackboard()
    agents = make_swarm(robot, seed, library, warm, use_llm, channels=unknown_body) if condition == "swarm" else None
    single = SingleAgent(robot, "chain" if condition == "single" else "mlp", seed=seed, any_types=unknown_body) \
        if condition in ("single", "mlp") else None
    curve, events, pending = [], [], sorted(eval_at)
    damaged = False
    t0 = time.time()

    def champion():
        if single is not None:
            return single.model
        c = bb.latest("champion")
        return c.payload["_model"] if c else None

    for t in range(max_ticks):
        if damage and not damaged and robot.motions >= damage[0]:
            desc = robot.damage(damage[1], seed)
            targets = reachable_targets(robot, n_targets, seed + 1)
            events.append({"motion": robot.motions, "event": "damage", "what": desc})
            damaged = True
        before = robot.motions
        if single is not None:
            single.step(t)
        else:
            for i in rng.permutation(len(agents)):
                agents[i].step(bb, t)
        if on_tick is not None:
            on_tick(bb, robot, t, events)
        while pending and robot.motions >= pending[0]:
            m = champion()
            err = float(np.median(reach_errors(robot, m, targets, robot.n_channels, seed))) * 1000 \
                if m is not None else np.nan
            curve.append((pending.pop(0), err))
            if verbose:
                print(f"  [{condition}] motions={robot.motions:3d} reach={err:7.1f} mm  ({time.time() - t0:.0f}s)")
        if robot.motions >= budget or not pending:
            break
        if robot.motions == before and single is None and not any(n.open for n in bb.needs):
            # converged and quiet: let the monitor keep watching for free ticks
            continue
    out = {"curve": curve, "events": events, "blackboard": bb, "motions": robot.motions}
    if single is None:
        alarms = [a.payload["motion"] for a in bb.of("anomaly", epoch=-1)]
        out["alarms"] = alarms
        c = bb.latest("champion")
        out["champion"] = c.payload if c else None
    else:
        out["alarms"] = []
        out["champion"] = {"family": single.family,
                           "describe": single.model.describe() if single.model else None,
                           "_model": single.model}
    # pad the curve if the swarm went quiet (converged) before every checkpoint was reached
    for p in pending:
        m = champion()
        err = float(np.median(reach_errors(robot, m, targets, robot.n_channels, seed))) * 1000 if m else np.nan
        curve.append((p, err))
    return out
