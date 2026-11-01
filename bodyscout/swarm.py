"""Run one condition on one robot and record the learning curve.

Conditions (same robot, same motion budget, same scorer):
  swarm   : all agents on the blackboard, no central planner
  single  : one generalist agent; random motions, one chain model, no holdout, no monitor
  single_probe : one sequential agent; sweeps each channel the way the explorers probe, classifies it
                 with the channel agents' rule, builds the structure and chain order itself, then random
                 motions and one chain model on all its data: no holdout, validator or monitor
  pipeline: the swarm's components (channel sweeps and their rule, findings to structures, chain modeler,
            holdout validator, monitor) run by one orchestrator in a fixed order: no needs, one
            proposal per stage, one validator, no fallbacks
  mlp     : one agent; random motions, a neural network self model (the "just learn it" baseline)

faults (bodyscout/faults.py) are wired into whichever slot each condition has for them.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np

from .agents import (ORDER_EVERY, ChannelAgent, Explorer, FindingsHypothesizer, LibraryHypothesizer,
                     LLMHypothesizer, Modeler, Monitor, PriorHypothesizer, Validator, classify_sweep,
                     infer_order, llm_providers, order_from_board, order_key, resolve_limbs,
                     structures_from_findings)
from .blackboard import Blackboard
from .faults import Faults, FlippedChannelAgent, WrongHypothesizer
from .models import ChainModel, MLPModel
from .planning import reach_errors
from .world import reachable_targets


class SingleAgent:
    """Does everything itself, in one loop. Fair: same budget, same model code."""

    def __init__(self, robot, family="chain", batch=4, seed=0, any_types=False, can_fit=None):
        self.robot, self.family, self.batch, self.any_types = robot, family, batch, any_types
        self.rng = np.random.default_rng(seed)
        self.Q, self.X = [], []
        self.model = None
        self.seed = seed
        self.can_fit = can_fit or (lambda motions: True)  # fault hook: False once the modeler has crashed

    def step(self, t):
        lo, hi = self.robot.limits
        for q in self.rng.uniform(lo, hi, (self.batch, self.robot.n_channels)):
            self.Q.append(q)
            self.X.append(self.robot.move(q))
        Q, X = np.array(self.Q), np.array(self.X)
        if not self.can_fit(len(Q)):
            return
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

    def __init__(self, robot, batch=4, seed=0, report=None, can_fit=None):
        super().__init__(robot, "chain", batch, seed, any_types=True, can_fit=can_fit)
        self.report = report or (lambda ch, fields: fields)  # fault hook: how a finding gets reported
        self.findings, self.obs = {}, []  # obs mimic observation artifacts so infer_order reads them
        self.ch, self.attempt = 0, 0
        self.order_cache = {}
        self.limb_cache = {}

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
        self.findings[self.ch] = {"channel": self.ch, **self.report(self.ch, fields), "_id": self.obs[-1].id}
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

    def _limbs(self):
        """Limb grouping from this agent's own findings. None for a single marker."""
        n = self.robot.n_channels
        if len(self.findings) < n:
            return None
        key = sum(1 for o in self.obs if "probe" not in o.payload) // ORDER_EVERY
        if key not in self.limb_cache:
            self.limb_cache[key] = resolve_limbs(self.findings, self.obs, n)
        return self.limb_cache[key]

    def step(self, t):
        n = self.robot.n_channels
        if self.ch < n:
            self._probe()
        else:
            lo, hi = self.robot.limits
            for q in self.rng.uniform(lo, hi, (self.batch, n)):
                self._move(q)
        if len(self.Q) < 6 or not self.can_fit(len(self.Q)):
            return
        kw = {"patterns": structures_from_findings(self.findings, n)[: self.N_STRUCTURES]}
        limbs = self._limbs()
        if limbs is not None:
            kw["limbs"] = limbs
        else:
            order = self._order()
            if order is not None and order != list(range(n)):
                kw["order"] = order
        self.model = ChainModel(n, restarts=3, seed=self.seed + t, any_types=True).fit(
            np.array(self.Q), np.array(self.X), **kw)


class PipelineAgent:
    """The swarm's components wired as a fixed pipeline under one orchestrator, the strongest
    non-swarm design we could build from the same parts. Each tick runs, in order:
      1. probe    sweep the next channel with the explorers' probe values (bent pose if the tip barely
                  moved) and classify it with the channel agents' rule; once every channel is done,
                  collect a batch of random motions, every fourth kept for holdout like the explorers
      2. propose  structures from the findings; an LLM stage, when there is one, revises that list and
                  its answer is final (each stage takes the previous stage's output: no competition)
      3. model    fit the chain model with that list, the chain order and the limb grouping
      4. validate score it on the holdout set and crown it if it beats the champion (one validator,
                  no replay check, no vote)
      5. monitor  the swarm monitor's rule: a sentinel motion every 3 ticks, two surprises in a row
                  restart the pipeline on a new epoch
    No needs and no second instance of anything. Posts artifacts with parents only so scoring and
    provenance read it the way they read the swarm. Hooks (all default to no fault): `report(ch,
    fields)` is how a finding gets reported, `llm()` returns the LLM stage's structures or None,
    `can_fit(motions)` is False once the modeler has crashed."""

    N_STRUCTURES = 4
    name = "pipeline"

    def __init__(self, robot, batch=4, holdout_every=4, seed=0, report=None, llm=None, can_fit=None,
                 monitor_every=3, k_sigma=4.0, floor_mm=8.0):
        self.robot, self.batch, self.holdout_every, self.seed = robot, batch, holdout_every, seed
        self.report = report or (lambda ch, fields: fields)
        self.llm = llm or (lambda: None)
        self.can_fit = can_fit or (lambda motions: True)
        self.every, self.k, self.floor = monitor_every, k_sigma, floor_mm
        self.rng = np.random.default_rng(seed)
        self.mon_rng = np.random.default_rng(seed + 31)
        self.count, self.strikes, self.epoch = 0, 0, -1

    def _new_epoch(self, bb):
        self.epoch = bb.epoch
        self.ch, self.attempt, self.last_n = 0, 0, -1
        self.cache, self.hyps = {}, None
        self.sid = bb.post("source", "pipeline", {"source": "pipeline", "describes":
                           "fixed schedule: probe, propose, model, validate, monitor"}).id

    def _move(self, bb, author, q, parents, **tags):
        x = self.robot.move(q)
        return bb.post("observation", author, {"q": q, "x": x, **tags}, parents)

    def _probe(self, bb):
        n = self.robot.n_channels
        base = np.zeros(n) if self.attempt == 0 else np.full(n, 0.8)
        obs = []
        for v in Explorer.PROBE_VALUES:
            q = base.copy()
            q[self.ch] = v
            obs.append(self._move(bb, "pipeline-probe", q, [self.sid], split="train", probe=self.ch,
                                  attempt=self.attempt))
        fields, spread = classify_sweep(np.array([a.payload["x"] for a in obs]), self.attempt)
        if fields is None and self.attempt == 0:
            self.attempt = 1
            return
        if fields is None:
            fields = {"type": "?", "axis": "?", "conf": 0.0, "spread_mm": spread * 1000}
        bb.post("finding", "pipeline-channel", {"channel": self.ch, **self.report(self.ch, fields)},
                [a.id for a in obs])
        self.ch, self.attempt = self.ch + 1, 0

    def _collect(self, bb):
        lo, hi = self.robot.limits
        for q in self.rng.uniform(lo, hi, (self.batch, self.robot.n_channels)):
            self.count += 1
            n_hold = sum(1 for a in bb.of("observation") if a.payload["split"] == "holdout")
            warmup = n_hold < 3 and self.count % 2 == 0
            split = "holdout" if warmup or self.count % self.holdout_every == 0 else "train"
            self._move(bb, "pipeline-probe", q, [self.sid], split=split)

    def _propose(self, bb):
        """Structure list and the artifacts it came from; computed once per epoch (findings are final)."""
        if self.hyps is None:
            n = self.robot.n_channels
            arts = {a.payload["channel"]: a for a in bb.of("finding")}
            pats = structures_from_findings({ch: a.payload for ch, a in arts.items()}, n)[: self.N_STRUCTURES]
            hs = [bb.post("hypothesis", "pipeline-propose", {"pattern": p, "source": "channels", "rank": i},
                          [a.id for a in arts.values()]) for i, p in enumerate(pats)]
            revised = self.llm()
            if revised:  # the LLM stage reads the proposal and replaces it
                hs = [bb.post("hypothesis", "pipeline-llm", {"pattern": list(p), "source": "claude", "rank": i},
                              [h.id for h in hs]) for i, p in enumerate(revised[: self.N_STRUCTURES])]
            self.hyps = hs
        return [h.payload["pattern"] for h in self.hyps], [h.id for h in self.hyps]

    def _layout(self, bb):
        """Limb grouping or chain order from the findings, recomputed as mixed motions arrive."""
        n = self.robot.n_channels
        key = order_key(bb)
        if key not in self.cache:
            findings = {a.payload["channel"]: {**a.payload, "_id": a.id} for a in bb.of("finding")}
            limbs = resolve_limbs(findings, bb.of("observation"), n)
            if limbs is not None:
                self.cache[key] = ("limbs", limbs)
            else:
                found = order_from_board(bb, n)
                self.cache[key] = ("order", found[0] if found else None)
        return self.cache[key]

    def _model_and_validate(self, bb):
        n = self.robot.n_channels
        obs = [a for a in bb.of("observation") if a.payload["split"] == "train"]
        if len(obs) < 6 or len(obs) == self.last_n or not self.can_fit(Monitor.motions_seen(bb)):
            return
        Q, X, ids = np.array([a.payload["q"] for a in obs]), np.array([a.payload["x"] for a in obs]), [a.id for a in obs]
        patterns, used = self._propose(bb)
        kw = {"patterns": patterns}
        what, layout = self._layout(bb)
        if what == "limbs":
            kw["limbs"] = layout
        elif layout is not None and layout != list(range(n)):
            kw["order"] = layout
        prev = bb.of("champion", epoch=-1)
        kw["warm"] = prev[-1].payload["_model"].warm_state if prev else None
        model = ChainModel(n, restarts=3, seed=self.seed + len(Q), any_types=True)
        try:
            model.fit(Q, X, **kw)
        except Exception:
            return
        self.last_n = len(Q)
        art = bb.post("model", "pipeline-modeler", {"family": "chain", "_model": model, "_fit_kw": kw,
                                                    "n_train": len(Q), "train_rmse_mm": model.rmse(Q, X) * 1000,
                                                    "describe": model.describe()}, ids[-8:] + used)
        hold = [a for a in bb.of("observation") if a.payload["split"] == "holdout"]
        if len(hold) < 3:
            return
        Qh, Xh, hids = (np.array([a.payload["q"] for a in hold]), np.array([a.payload["x"] for a in hold]),
                        [a.id for a in hold])
        score = model.rmse(Qh, Xh) * 1000
        champ = bb.latest("champion")
        if champ is not None and champ.payload["_model"].rmse(Qh, Xh) * 1000 <= score:
            return
        bb.post("champion", "pipeline-validator", {"candidate": art.id, "family": "chain", "_model": model,
                                                   "holdout_mm": score, "n_holdout": len(hids),
                                                   "describe": art.payload["describe"], "votes": 1},
                [art.id] + hids)

    def _monitor(self, bb, t):
        champs = bb.of("champion")
        if not champs or t % self.every:
            return
        champ = min(champs, key=lambda c: (c.payload["holdout_mm"], c.id))
        q = self.mon_rng.uniform(*self.robot.limits, self.robot.n_channels)
        obs = self._move(bb, "pipeline-monitor", q, [champ.id], split="train")
        surprise = float(np.linalg.norm(champ.payload["_model"].predict(q[None])[0] - obs.payload["x"])) * 1000
        thresh = max(self.k * champ.payload["holdout_mm"], self.floor)
        self.strikes = self.strikes + 1 if surprise > thresh else 0
        if self.strikes >= 2:
            self.strikes = 0
            bb.post("anomaly", "pipeline-monitor", {"surprise_mm": surprise, "threshold_mm": thresh,
                                                    "motion": Monitor.motions_seen(bb)}, [obs.id, champ.id])
            bb.new_epoch()
            bb.post("observation", "pipeline-monitor", {"q": q, "x": obs.payload["x"], "split": "train",
                                                        "carried": True}, [obs.id])

    def step(self, bb, t):
        if bb.epoch != self.epoch:
            self._new_epoch(bb)
        if self.ch < self.robot.n_channels:
            self._probe(bb)
        else:
            self._collect(bb)
            self._model_and_validate(bb)
        self._monitor(bb, t)
        return True


def make_swarm(robot, seed=0, library=None, warm=None, use_llm=None, families=("chain", "gmm", "mlp"),
               monitor=True, explore="disagreement", channels=False, n_explorers=2, n_validators=2,
               dynamics=False):
    """channels=True: the body type is unknown, so one agent per channel works out hinge or slide.
    dynamics=True: also learn and watch the body's dynamics (robot needs move_trajectory and dt,
    e.g. bodyscout.dynamics.world_dyn.DynamicRobot); the Exciter serves the modeler's excitation need.
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
    if dynamics:
        from .dynamics.agents_dyn import DynamicsModeler, DynamicsMonitor, Exciter
        agents += [Exciter(robot, seed), DynamicsModeler(n, seed=seed), DynamicsMonitor(robot, seed=seed)]
    return agents


def run(robot, condition="swarm", budget=64, eval_at=(8, 12, 16, 24, 32, 48, 64), n_targets=12,
        seed=0, damage=None, library=None, warm=None, use_llm=None, max_ticks=400, verbose=False,
        on_tick=None, unknown_body=False, knockout=None, faults=None):
    """damage = (motion_count, kind). knockout = (motion_count, [agent names]) removes those swarm
    agents once that many motions are spent. faults = a name or list from bodyscout.faults.FAULTS.
    Returns dict with curve [(motions, median_reach_mm)], blackboard, motions, agent_s (wall) and
    agent_cpu_s (process CPU) spent in agent steps, and fault_hits (how often each fault fired)."""
    rng = np.random.default_rng(seed)
    fx = Faults(faults, robot, seed)
    robot = fx.wrap(robot)  # noisy_channel: the agents see a bad camera on one channel's sweeps
    targets = reachable_targets(robot, n_targets, seed)
    bb = Blackboard()
    def can_fit(motions):
        if fx.crashed(motions):
            fx.hit("modeler_crash")
            return False
        return True

    def bad_llm_stage():
        fx.hit("bad_llm")
        return fx.wrong_structures()

    hooks = {"report": fx.finding, "can_fit": can_fit}
    agents = single = None
    if condition == "swarm":
        agents = make_swarm(robot, seed, library, warm, use_llm, channels=unknown_body)
        if "wrong_finding" in fx:
            agents = [FlippedChannelAgent(a, fx) if a.name == f"channel-{fx.channel}" else a for a in agents]
        if "bad_llm" in fx:
            agents.append(WrongHypothesizer(robot.n_channels, fx))
    elif condition == "pipeline":
        agents = [PipelineAgent(robot, seed=seed, llm=bad_llm_stage if "bad_llm" in fx else None, **hooks)]
    elif condition == "single_probe":
        single = SingleProbeAgent(robot, seed=seed, **hooks)
    elif condition in ("single", "mlp"):
        single = SingleAgent(robot, "chain" if condition == "single" else "mlp", seed=seed,
                             any_types=unknown_body, can_fit=hooks["can_fit"])
    else:
        raise ValueError(condition)
    curve, events, pending = [], [], sorted(eval_at)
    damaged = False
    champion_before = None
    t0 = time.time()
    agent_s = agent_cpu = 0.0  # time spent in agent steps only, so scoring checkpoints do not count
    multi = np.asarray(targets).ndim == 3  # one column of xyz per fingertip
    limb_curve = []

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

    def score(model):
        """Median reach error in mm, and per fingertip when the body has several."""
        n_tips = int(targets.shape[1]) if multi else 0
        if model is None:
            return np.nan, [np.nan] * n_tips
        raw = reach_errors(robot, model, targets, robot.n_channels, seed)
        if raw.ndim == 1:
            return float(np.median(raw)) * 1000, None
        per = [float(v) * 1000 for v in np.median(raw, axis=0)]
        return float(np.median(raw)) * 1000, per

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
        if condition == "swarm" and fx.crashed(robot.motions) and any(a.name == "modeler-chain" for a in agents):
            agents = [a for a in agents if a.name != "modeler-chain"]
            fx.hit("modeler_crash")
            events.append({"motion": robot.motions, "event": "fault", "what": "modeler_crash"})
        before = robot.motions
        ts, tc = time.perf_counter(), time.process_time()
        if single is not None:
            single.step(t)
        else:
            for i in rng.permutation(len(agents)):
                agents[i].step(bb, t)
        agent_s += time.perf_counter() - ts
        agent_cpu += time.process_time() - tc
        if on_tick is not None:
            on_tick(bb, robot, t, events)
        while pending and robot.motions >= pending[0]:
            err, per = score(champion())
            motion = pending.pop(0)
            curve.append((motion, err))
            if multi:
                limb_curve.append((motion, per))
            if verbose:
                print(f"  [{condition}] motions={robot.motions:3d} reach={err:7.1f} mm  ({time.time() - t0:.0f}s)")
        if robot.motions >= budget or not pending:
            break
        if robot.motions == before and single is None and not any(n.open for n in bb.needs):
            # converged and quiet: let the monitor keep watching for free ticks
            continue
    out = {"curve": curve, "events": events, "blackboard": bb, "motions": robot.motions,
           "agent_s": agent_s, "agent_cpu_s": agent_cpu, "champion_before": champion_before,
           "fault_hits": dict(fx.hits)}
    if multi:
        out["limb_curve"] = limb_curve
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
        err, per = score(champion())
        curve.append((p, err))
        if multi:
            limb_curve.append((p, per))
    return out
