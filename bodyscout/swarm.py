"""Run one condition on one robot and record the learning curve.

Conditions (same robot, same motion budget, same scorer):
  swarm   : all agents on the blackboard, no central planner
  single  : one generalist agent; random motions, one chain model, no holdout, no monitor
  single_probe : one sequential agent; sweeps each channel the way the explorers probe, classifies it
                 with the channel agents' rule, builds the structure and chain order itself, then random
                 motions and one chain model on all its data: no holdout, validator or monitor
  mlp     : one agent; random motions, a neural network self model (the "just learn it" baseline)
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np

from .agents import (ORDER_EVERY, ChannelAgent, Explorer, FindingsHypothesizer, LibraryHypothesizer,
                     LLMHypothesizer, Modeler, Monitor, PriorHypothesizer, Validator, classify_sweep,
                     infer_order, llm_providers, structures_from_findings)
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


class SingleProbeAgent(SingleAgent):
    """The swarm's structure discovery done by one agent in one loop: sweep channel after channel with
    the explorers' probe values (bent base pose when the tip barely moves), classify each sweep with
    the channel agents' rule, assemble structures and the chain order itself, then spend the rest on
    random motions. One chain model refit on all data each step; no holdout, validator or monitor."""

    N_STRUCTURES = 4

    def __init__(self, robot, batch=4, seed=0):
        super().__init__(robot, "chain", batch, seed, any_types=True)
        self.findings, self.obs = {}, []  # obs mimic observation artifacts so infer_order reads them
        self.ch, self.attempt = 0, 0
        self.order_cache = {}

    def _move(self, q, **tags):
        x = self.robot.move(q)
        self.Q.append(q)
        self.X.append(x)
        self.obs.append(SimpleNamespace(id=len(self.obs), payload={"q": q, "x": x, "split": "train", **tags}))
        return x

    def _probe(self):
        n = self.robot.n_channels
        base = np.zeros(n) if self.attempt == 0 else np.full(n, 0.8)
        P = []
        for v in Explorer.PROBE_VALUES:
            q = base.copy()
            q[self.ch] = v
            P.append(self._move(q, probe=self.ch, attempt=self.attempt))
        fields, spread = classify_sweep(np.array(P), self.attempt)
        if fields is None and self.attempt == 0:
            self.attempt = 1
            return
        if fields is None:
            fields = {"type": "?", "axis": "?", "conf": 0.0, "spread_mm": spread * 1000}
        self.findings[self.ch] = {"channel": self.ch, **fields, "_id": self.obs[-1].id}
        self.ch, self.attempt = self.ch + 1, 0

    def _order(self):
        n = self.robot.n_channels
        if len(self.findings) < n:
            return None
        key = sum(1 for o in self.obs if "probe" not in o.payload) // ORDER_EVERY
        if key not in self.order_cache:
            found = infer_order(self.findings, self.obs, n)
            self.order_cache[key] = found[0] if found else None
        return self.order_cache[key]

    def step(self, t):
        n = self.robot.n_channels
        if self.ch < n:
            self._probe()
        else:
            lo, hi = self.robot.limits
            for q in self.rng.uniform(lo, hi, (self.batch, n)):
                self._move(q)
        if len(self.Q) < 6:
            return
        kw = {"patterns": structures_from_findings(self.findings, n)[: self.N_STRUCTURES]}
        order = self._order()
        if order is not None and order != list(range(n)):
            kw["order"] = order
        self.model = ChainModel(n, restarts=3, seed=self.seed + t, any_types=True).fit(
            np.array(self.Q), np.array(self.X), **kw)


def make_swarm(robot, seed=0, library=None, warm=None, use_llm=None, families=("chain", "gmm", "mlp"),
               monitor=True, explore="disagreement", channels=False, n_explorers=2, n_validators=2):
    """channels=True: the body type is unknown, so one agent per channel works out hinge or slide.
    use_llm: None = one LLM hypothesizer per provider with an API key, False = none, True = those
    providers, or Claude if no key is set (its calls then fail quietly)."""
    n = robot.n_channels
    providers = [] if use_llm is False else (llm_providers() or (["claude"] if use_llm else []))
    agents = ([FindingsHypothesizer(n)] if channels else []) + [
        PriorHypothesizer(n), LibraryHypothesizer(n, library),
        *[LLMHypothesizer(n, p) for p in providers],
        *[Explorer(robot, mode=explore, seed=seed + 101 * i, name=f"explorer-{i}") for i in range(n_explorers)],
        *[Modeler(f, n, seed=seed, warm=warm if f == "chain" else None, any_types=channels) for f in families],
        *[Validator(n, seed=seed, index=i) for i in range(n_validators)]]
    if channels:
        agents += [ChannelAgent(i, n) for i in range(n)]
    if monitor:
        agents.append(Monitor(robot, seed=seed))
    return agents


def run(robot, condition="swarm", budget=64, eval_at=(8, 12, 16, 24, 32, 48, 64), n_targets=12,
        seed=0, damage=None, library=None, warm=None, use_llm=None, max_ticks=400, verbose=False,
        on_tick=None, unknown_body=False, knockout=None):
    """damage = (motion_count, kind). knockout = (motion_count, [agent names]) removes those swarm
    agents once that many motions are spent. Returns dict with curve [(motions, median_reach_mm)],
    blackboard."""
    rng = np.random.default_rng(seed)
    targets = reachable_targets(robot, n_targets, seed)
    bb = Blackboard()
    agents = make_swarm(robot, seed, library, warm, use_llm, channels=unknown_body) if condition == "swarm" else None
    single = SingleAgent(robot, "chain" if condition == "single" else "mlp", seed=seed, any_types=unknown_body) \
        if condition in ("single", "mlp", "single_probe") else None
    curve, events, pending = [], [], sorted(eval_at)
    damaged = False
    champion_before = None
    t0 = time.time()
    agent_s = 0.0  # time spent in agent steps only, so scoring checkpoints do not count

    def champion():
        if single is not None:
            return single.model
        c = bb.latest("champion")
        return c.payload["_model"] if c else None

    def freeze_champion():
        """The self model as it stands before damage. A new dict, so later refits keep their own."""
        if single is not None:
            m = single.model
            if m is None:
                return None
            return {"family": single.family, "_model": m, "describe": m.describe(),
                    "holdout_mm": None, "n_holdout": 0, "candidate": None, "votes": 0}
        c = bb.latest("champion")
        return None if c is None else dict(c.payload)

    for t in range(max_ticks):
        if damage and not damaged and robot.motions >= damage[0]:
            champion_before = freeze_champion()
            desc = robot.damage(damage[1], seed)
            targets = reachable_targets(robot, n_targets, seed + 1)
            events.append({"motion": robot.motions, "event": "damage", "what": desc})
            damaged = True
        if knockout and agents and robot.motions >= knockout[0] and not any(e["event"] == "knockout" for e in events):
            gone = [a.name for a in agents if a.name in knockout[1]]
            agents = [a for a in agents if a.name not in knockout[1]]
            events.append({"motion": robot.motions, "event": "knockout", "what": gone})
        before = robot.motions
        ts = time.perf_counter()
        if single is not None:
            single.step(t)
        else:
            for i in rng.permutation(len(agents)):
                agents[i].step(bb, t)
        agent_s += time.perf_counter() - ts
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
    out = {"curve": curve, "events": events, "blackboard": bb, "motions": robot.motions,
           "agent_s": agent_s, "champion_before": champion_before}
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
