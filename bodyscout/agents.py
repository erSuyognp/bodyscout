"""The swarm. Each agent owns one job, reads the blackboard, and posts artifacts. No planner.

Explorer     owns the robot channels; serves `probe` and `data` needs with motions
Channel x N  one per unlabeled channel: wiggles only its channel, decides hinge or slide and the axis
Hypothesizer assembles channel findings into whole body structures; uses Claude when a key is set
Modeler x3   chain / gmm / mlp; refits when new data lands, posts candidate self models
Validator    scores candidates on held out motions, applies the replay gate, crowns a champion
Monitor      spends a sentinel motion now and then; declares "my body changed" on surprise
"""
from __future__ import annotations

import itertools
import json
import os
import re

import numpy as np

from .blackboard import Blackboard
from .models import FAMILIES, ChainModel


class Agent:
    name = "agent"

    def step(self, bb: Blackboard, t: int) -> bool:
        raise NotImplementedError


def _data(bb: Blackboard, split: str):
    obs = [a for a in bb.of("observation") if a.payload["split"] == split]
    if not obs:
        return np.zeros((0, 0)), np.zeros((0, 3)), []
    return (np.array([a.payload["q"] for a in obs]), np.array([a.payload["x"] for a in obs]),
            [a.id for a in obs])


def current_score(bb: Blackboard, champ) -> dict:
    """Latest holdout score for a champion: its newest `score` artifact, else the crowning score.
    Artifacts are immutable, so re-scoring posts a new `score` instead of editing the champion."""
    scores = [a for a in bb.of("score", epoch=-1) if a.payload["champion"] == champ.id]
    src = scores[-1].payload if scores else champ.payload
    return {"holdout_mm": src["holdout_mm"], "n_holdout": src["n_holdout"]}


# ---------------------------------------------------------------------------
class Explorer(Agent):
    name = "explorer"

    def __init__(self, robot, batch=4, holdout_every=4, mode="disagreement", seed=0):
        self.robot, self.batch, self.holdout_every, self.mode = robot, batch, holdout_every, mode
        self.rng = np.random.default_rng(seed)
        self.count = 0

    def _choose(self, bb):
        n = self.robot.n_channels
        lo, hi = self.robot.limits
        cands = self.rng.uniform(lo, hi, (300, n))
        if self.mode == "random":
            return cands[: self.batch]
        Q, _, _ = _data(bb, "train")
        models = [a.payload["_model"] for a in bb.of("model")[-3:]]
        if len(Q) < 6 or len(models) < 2:
            return cands[: self.batch]
        preds = np.stack([m.predict(cands) for m in models])          # (k, C, 3)
        disagree = np.linalg.norm(preds.std(0), axis=1)
        cover = np.min(np.linalg.norm(cands[:, None] - Q[None], axis=2), axis=1)
        score = disagree / (disagree.std() + 1e-9) + cover / (cover.std() + 1e-9)
        chosen = []
        for i in np.argsort(-score):  # greedy, keep the batch spread out
            if all(np.linalg.norm(cands[i] - cands[j]) > 0.6 for j in chosen):
                chosen.append(i)
            if len(chosen) == self.batch:
                break
        return cands[chosen]

    PROBE_VALUES = (-1.5, -0.5, 0.5, 1.5)  # never 0: the base pose would repeat for every channel

    def _probe(self, bb, need):
        """Sweep one channel with every other channel held at a base pose."""
        n = self.robot.n_channels
        ch, attempt = need.payload["channel"], need.payload["attempt"]
        base = np.zeros(n) if attempt == 0 else np.full(n, 0.8)
        for v in self.PROBE_VALUES:
            q = base.copy()
            q[ch] = v
            x = self.robot.move(q)
            bb.post("observation", self.name, {"q": q, "x": x, "split": "train", "probe": ch,
                                               "attempt": attempt}, [need.id])

    def step(self, bb, t):
        need = bb.claim_prefix("probe:")
        if need is not None:
            self._probe(bb, need)
            return True
        need = bb.claim("data")
        if need is None:
            return False
        for q in self._choose(bb):
            x = self.robot.move(q)
            self.count += 1
            n_hold = sum(1 for a in bb.of("observation") if a.payload["split"] == "holdout")
            warmup = n_hold < 3 and self.count % 2 == 0  # fill a minimal holdout set quickly
            split = "holdout" if warmup or self.count % self.holdout_every == 0 else "train"
            bb.post("observation", self.name, {"q": q, "x": x, "split": split}, [need.id])
        return True


# ---------------------------------------------------------------------------
class ChannelAgent(Agent):
    """Owns one unlabeled channel. Asks for a sweep of only that channel, then reads the shape of
    the fingertip path: a straight line means the joint slides, an arc means it rotates. The line
    direction (slide) or the arc's plane normal (hinge) gives the axis. Knows nothing about other
    channels; the hypothesizer assembles everyone's findings into a whole body."""

    def __init__(self, channel, n):
        self.ch, self.n = channel, n
        self.name = f"channel-{channel}"
        self.epoch, self.attempt, self.requested, self.done = -1, 0, False, False

    def step(self, bb, t):
        if bb.epoch != self.epoch:
            self.epoch, self.attempt, self.requested, self.done = bb.epoch, 0, False, False
        if self.done:
            return False
        obs = [a for a in bb.of("observation")
               if a.payload.get("probe") == self.ch and a.payload.get("attempt") == self.attempt]
        if len(obs) < len(Explorer.PROBE_VALUES):
            if not self.requested:
                bb.need(f"probe:{self.ch}", self.name, 200.0 - self.ch, channel=self.ch, attempt=self.attempt)
                self.requested = True
            return False
        P = np.array([a.payload["x"] for a in obs])
        _, sv, vt = np.linalg.svd(P - P.mean(0))
        spread = float(sv[0])
        if spread < 0.006:  # the tip barely moved from this pose: look again from a bent pose
            if self.attempt == 0:
                self.attempt, self.requested = 1, False
                return True
            bb.post("finding", self.name, {"channel": self.ch, "type": "?", "axis": "?", "conf": 0.0,
                                           "spread_mm": spread * 1000}, [a.id for a in obs])
            self.done = True
            return True
        ratio = float(sv[1] / sv[0])
        kind = "s" if ratio < 0.12 else "h"
        direction = vt[0] if kind == "s" else vt[2]
        axis = "xyz"[int(np.argmax(np.abs(direction)))]
        conf = float(np.max(np.abs(direction))) if self.attempt == 0 else 0.0  # bent pose: frame differs
        bb.post("finding", self.name, {"channel": self.ch, "type": kind, "axis": axis, "conf": conf,
                                       "curvature": ratio, "spread_mm": spread * 1000}, [a.id for a in obs])
        self.done = True
        return True


# ---------------------------------------------------------------------------
class Hypothesizer(Agent):
    """Proposes which axis each unlabeled channel turns about. Ranked by the skill library
    (bodies seen before), then by Claude reading the raw data, then a plain prior."""

    name = "hypothesizer"

    def __init__(self, n, library=None, use_llm=None, top=4, wait_for_channels=False):
        self.n, self.top = n, top
        self.library = library if library is not None else []
        self.use_llm = bool(os.environ.get("ANTHROPIC_API_KEY")) if use_llm is None else use_llm
        self.done_epoch = -1
        self.wait = wait_for_channels
        self.sources_epoch, self.source_ids = -1, {}

    def _from_findings(self, findings):
        """Turn per channel findings into ranked whole body structures (fewest guesses first)."""
        opts = []
        for ch in range(self.n):
            f = findings.get(ch)
            if f is None or f["type"] == "?":
                opts.append([(t + a, 1) for t in "hs" for a in "zyx"])
            elif f["conf"] >= 0.85:
                opts.append([(f["type"] + f["axis"], 0)])
            else:
                opts.append([(f["type"] + a, 0 if a == f["axis"] else 1) for a in "zyx"])
        combos = []
        for combo in itertools.product(*opts):
            combos.append((sum(c[1] for c in combo), [c[0] for c in combo]))
            if len(combos) > 500:
                break
        combos.sort(key=lambda c: c[0])
        return [c[1] for c in combos]

    def _prior(self):
        pats = [["z"] + list(p) for p in itertools.product("yxz", repeat=self.n - 1)]
        return sorted(pats, key=lambda p: -sum(c == "y" for c in p))

    def _llm(self, bb):
        """Returns (patterns, ids of the observations shown to the model)."""
        Q, X, ids = _data(bb, "train")
        if len(Q) < 6:
            return [], []
        try:
            import anthropic
            rows = "\n".join(f"q={np.round(q, 2).tolist()} -> tip_mm={np.round(x * 1000).astype(int).tolist()}"
                             for q, x in zip(Q[:24], X[:24]))
            prompt = (
                f"A jointed robot of unknown type has {self.n} unlabeled channels and we observe its "
                f"fingertip in mm (z up, base at origin). Each channel either rotates (h) or slides (s) "
                f"about or along x, y or z in the base pose frame. Propose the {self.top} most likely "
                f"structures, one token per channel such as hz or sx. Reason about which channels move "
                f"the tip in arcs versus straight lines.\n{rows}\n"
                'Answer ONLY with JSON like {"patterns": [["hz","hy","sz"]], "why": "one sentence"}')
            msg = anthropic.Anthropic().messages.create(
                model=os.environ.get("BODYSCOUT_MODEL", "claude-sonnet-5-5"), max_tokens=600,
                messages=[{"role": "user", "content": prompt}])
            text = msg.content[0].text
            js = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            pats = [p for p in js["patterns"] if len(p) == self.n]
            self.last_why = js.get("why", "")
            return pats, ids[:24]
        except Exception as e:  # never let the LLM take the swarm down
            self.last_why = f"llm unavailable: {type(e).__name__}"
            return [], []

    def _source_id(self, bb, src):
        """Id of this epoch's `source` artifact for a prior or the library, posted on first use,
        so hypotheses that come from no data still cite where they came from."""
        if self.sources_epoch != bb.epoch:
            self.sources_epoch, self.source_ids = bb.epoch, {}
        if src not in self.source_ids:
            what = ("default ranking: base yaw, then most pitch (y) joints first" if src == "prior"
                    else f"skill library of bodies seen before: {self.library}")
            self.source_ids[src] = bb.post("source", self.name, {"source": src, "describes": what}).id
        return self.source_ids[src]

    def step(self, bb, t):
        if self.done_epoch == bb.epoch and not bb.has_need("hypotheses"):
            return False
        finding_arts = {a.payload["channel"]: a for a in bb.of("finding")}
        if self.wait and len(finding_arts) < self.n and self.done_epoch != bb.epoch:
            return False  # let the channel agents report first
        bb.claim("hypotheses")
        ranked, seen = [], set()
        findings = {ch: a.payload for ch, a in finding_arts.items()}
        finding_ids = [a.id for a in finding_arts.values()]
        sources = [(p, "channels", finding_ids) for p in self._from_findings(findings)] if findings else []
        sources += [(p, "library", None) for p in self.library]
        if self.use_llm and self.done_epoch == bb.epoch:  # second pass in an epoch: ask Claude
            pats, shown = self._llm(bb)
            sources += [(p, "claude", shown) for p in pats]
        sources += [(p, "prior", None) for p in self._prior()]
        for p, src, parents in sources:
            p = [c if len(c) == 2 else "h" + c for c in p]
            if tuple(p) not in seen and len(p) == self.n:
                seen.add(tuple(p))
                ranked.append((p, src, parents))
        for p, src, parents in ranked[: self.top]:
            bb.post("hypothesis", self.name, {"pattern": p, "source": src},
                    parents if parents else [self._source_id(bb, src)])
        self.done_epoch = bb.epoch
        return True


# ---------------------------------------------------------------------------
class Modeler(Agent):
    MIN_DATA = {"chain": 6, "gmm": 28, "mlp": 16}

    def __init__(self, family, n, seed=0, warm=None, any_types=False):
        self.family, self.n, self.seed, self.any_types = family, n, seed, any_types
        self.name = f"modeler-{family}"
        self.last_n = -1
        self.last_epoch = -1
        self.warm = warm  # parameters carried over from a previous body (transfer)

    def step(self, bb, t):
        Q, X, ids = _data(bb, "train")
        if bb.epoch != self.last_epoch:
            self.last_n, self.last_epoch = -1, bb.epoch
        if len(Q) < self.MIN_DATA[self.family] or len(Q) == self.last_n:
            return False
        kw = {}
        hyps = bb.of("hypothesis")
        if self.family == "chain":
            kw["patterns"] = [h.payload["pattern"] for h in hyps[-4:]]
            prev = [a for a in bb.of("champion", epoch=-1) if a.payload["family"] == "chain"]
            kw["warm"] = prev[-1].payload["_model"].warm_state if prev else self.warm
            model = ChainModel(self.n, restarts=3, seed=self.seed + len(Q), any_types=self.any_types)
        else:
            model = FAMILIES[self.family](self.n, seed=self.seed)
        try:
            model.fit(Q, X, **kw)
        except Exception:
            return False
        self.last_n = len(Q)
        train = model.rmse(Q, X)
        bb.post("model", self.name, {"family": self.family, "_model": model, "_fit_kw": kw,
                                     "n_train": len(Q), "train_rmse_mm": train * 1000,
                                     "describe": model.describe()}, ids[-8:] + [h.id for h in hyps[-4:]])
        return True


# ---------------------------------------------------------------------------
class Validator(Agent):
    """Holdout scoring plus a replay gate: a candidate is crowned only if refitting it from scratch
    on the same data reproduces its holdout score, and it beats the current champion."""

    name = "validator"

    def __init__(self, n, goal_mm=4.0, seed=0):
        self.n, self.goal_mm, self.seed = n, goal_mm, seed
        self.seen = set()

    def _replay(self, art, Q, X, Qh, Xh):
        fam = art.payload["family"]
        m = (ChainModel(self.n, restarts=3, seed=self.seed + 7777) if fam == "chain"
             else FAMILIES[fam](self.n, seed=self.seed + 7777))
        m.fit(Q, X, **art.payload["_fit_kw"])
        return m.rmse(Qh, Xh) * 1000

    def step(self, bb, t):
        Qh, Xh, hids = _data(bb, "holdout")
        champ = bb.latest("champion")
        if not bb.of("observation"):
            bb.need("data", self.name, 1.0, why="no data yet")
            return True
        new = [a for a in bb.of("model") if a.id not in self.seen]
        if len(Qh) < 3:
            bb.need("data", self.name, 1.0, why="need holdout motions")
            return False
        if not new:
            # holdout set grew since the champion was judged: re-score it honestly
            if champ is not None and current_score(bb, champ)["n_holdout"] < len(Qh):
                score = champ.payload["_model"].rmse(Qh, Xh) * 1000
                bb.post("score", self.name, {"champion": champ.id, "holdout_mm": score,
                                             "n_holdout": len(Qh)}, [champ.id] + hids)
            champ_mm = current_score(bb, champ)["holdout_mm"] if champ else None
            if champ is None or champ_mm > self.goal_mm:
                bb.need("data", self.name, champ_mm if champ else 50.0)
            return False
        Q, X, _ = _data(bb, "train")
        for art in new:
            self.seen.add(art.id)
            if art.payload["n_train"] != len(Q):
                continue  # stale candidate, fit on older data
            score = art.payload["_model"].rmse(Qh, Xh) * 1000
            ok_replay = True
            beats = champ is None or score < 0.95 * current_score(bb, champ)["holdout_mm"]
            if beats:
                rep = self._replay(art, Q, X, Qh, Xh)
                ok_replay = rep <= max(1.5 * score, score + 2.0)
            bb.post("verdict", self.name, {"candidate": art.id, "family": art.payload["family"],
                                           "holdout_mm": score, "replayed": ok_replay,
                                           "crowned": bool(beats and ok_replay)}, [art.id] + hids)
            if beats and ok_replay:
                champ = bb.post("champion", self.name, {"family": art.payload["family"],
                                                        "_model": art.payload["_model"],
                                                        "holdout_mm": score, "n_holdout": len(Qh),
                                                        "describe": art.payload["describe"]}, [art.id])
        champ_mm = current_score(bb, champ)["holdout_mm"] if champ else None
        if champ is None:
            bb.need("data", self.name, 50.0)
        elif champ_mm > self.goal_mm:
            bb.need("data", self.name, champ_mm)
            if champ_mm > 4 * self.goal_mm and len(Q) >= 12:
                bb.need("hypotheses", self.name, 1.0, why="chain fits are poor, rethink structure")
        return True


# ---------------------------------------------------------------------------
class Monitor(Agent):
    """Spends one sentinel motion every `every` ticks once a champion exists."""

    name = "monitor"

    def __init__(self, robot, every=3, k_sigma=4.0, floor_mm=8.0, seed=0):
        self.robot, self.every, self.k, self.floor = robot, every, k_sigma, floor_mm
        self.rng = np.random.default_rng(seed + 31)
        self.strikes = 0
        self.alarms = []

    @staticmethod
    def motions_seen(bb):
        """Motions the swarm has spent, counted from its own records (every move posts one
        observation; the copy carried into a new epoch is not a new motion)."""
        return sum(1 for a in bb.of("observation", epoch=-1) if not a.payload.get("carried"))

    def step(self, bb, t):
        champ = bb.latest("champion")
        if champ is None or t % self.every:
            return False
        q = self.rng.uniform(*self.robot.limits, self.robot.n_channels)
        x = self.robot.move(q)
        pred = champ.payload["_model"].predict(q[None])[0]
        surprise = float(np.linalg.norm(pred - x)) * 1000
        thresh = max(self.k * current_score(bb, champ)["holdout_mm"], self.floor)
        obs = bb.post("observation", self.name, {"q": q, "x": x, "split": "train",
                                                  "surprise_mm": surprise}, [champ.id])
        self.strikes = self.strikes + 1 if surprise > thresh else 0
        if self.strikes >= 2:
            self.strikes = 0
            motion = self.motions_seen(bb)
            bb.post("anomaly", self.name, {"surprise_mm": surprise, "threshold_mm": thresh,
                                           "motion": motion}, [obs.id, champ.id])
            self.alarms.append(motion)
            bb.new_epoch()
            bb.post("observation", self.name, {"q": q, "x": x, "split": "train", "carried": True},
                    [obs.id])
            bb.need("data", self.name, 100.0, why="body changed")
            bb.need("hypotheses", self.name, 1.0, why="body changed")
        return True
