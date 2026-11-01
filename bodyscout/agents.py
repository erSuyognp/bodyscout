"""The swarm. Each agent owns one job, reads the blackboard, and posts artifacts. No planner, and no
single agent whose loss stops the swarm: every role has a second instance or a fallback.

Explorer x2     share the robot through needs; serve `probe` and `data` needs with motions
Channel x N     one per unlabeled channel: wiggles only its channel, decides hinge or slide and the axis
Hypothesizers   independent; each posts hypotheses tagged by source: findings (assembles channel
                findings), prior, library, and one LLM agent per API key (Claude, Gemini)
Modeler x3      chain / gmm / mlp; refit when new data lands. The chain modeler reads hypotheses, and
                assembles channel findings itself when no findings hypothesizer has
Validator x2    replay check candidates and vote for crown(bb), a public pure rule; a champion is
                posted only when the live validators agree
Monitor         spends a sentinel motion now and then; declares "my body changed" on surprise
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import re

import numpy as np

from .blackboard import Blackboard
from .models import FAMILIES, ChainModel, _tok


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
    def __init__(self, robot, batch=4, holdout_every=4, mode="disagreement", seed=0, name="explorer"):
        self.robot, self.batch, self.holdout_every, self.mode = robot, batch, holdout_every, mode
        self.name = name
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
    channels; hypothesizers and the chain modeler assemble everyone's findings into a whole body."""

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
# Hypothesizers: independent proposers. Each posts hypotheses tagged with its source, none waits on
# another, and the chain modeler can stand in for the findings one (see Modeler._structures).

SOURCE_ORDER = ("channels", "library", "claude", "gemini", "prior")  # how modelers rank sources
LLM_KEYS = {"claude": ("ANTHROPIC_API_KEY",), "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY")}


def llm_providers() -> list:
    """LLM hypothesizers this machine can run: one per provider whose API key is set."""
    return [p for p, keys in LLM_KEYS.items() if any(os.environ.get(k) for k in keys)]


def structures_from_findings(findings: dict, n: int) -> list:
    """Turn per channel findings {channel: payload} into ranked whole body structures, fewest
    guesses first. Shared by the findings hypothesizer and the chain modeler's fallback."""
    opts = []
    for ch in range(n):
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


def prior_structures(n: int) -> list:
    pats = [["hz"] + ["h" + c for c in p] for p in itertools.product("yxz", repeat=n - 1)]
    return sorted(pats, key=lambda p: -sum(c == "hy" for c in p))


class HypothesizerBase(Agent):
    source = "?"

    def __init__(self, n, top=4):
        self.n, self.top = n, top
        self.name = f"hyp-{self.source}"
        self.done = set()               # (epoch, input key) already answered
        self.source_ids = {}            # epoch -> id of this agent's `source` artifact

    def _source_id(self, bb, describes):
        """This epoch's `source` artifact, so hypotheses that come from no data still cite their origin."""
        if bb.epoch not in self.source_ids:
            self.source_ids[bb.epoch] = bb.post("source", self.name, {"source": self.source,
                                                                      "describes": describes}).id
        return self.source_ids[bb.epoch]

    def _post(self, bb, patterns, parents):
        seen, n_posted = set(), 0
        for p in patterns:
            p = [_tok(c) for c in p]
            if len(p) != self.n or tuple(p) in seen:
                continue
            seen.add(tuple(p))
            bb.post("hypothesis", self.name, {"pattern": p, "source": self.source, "rank": n_posted},
                    parents)
            n_posted += 1
            if n_posted == self.top:
                break
        return n_posted > 0


class FindingsHypothesizer(HypothesizerBase):
    """Assembles the channel agents' findings into whole body structures."""

    source = "channels"

    def step(self, bb, t):
        arts = {a.payload["channel"]: a for a in bb.of("finding")}
        if not arts:
            return False
        if len(arts) < self.n and not bb.has_need("hypotheses"):
            return False  # waits for channel agents, never for another hypothesizer
        key = (bb.epoch, tuple(sorted(a.id for a in arts.values())))
        if key in self.done:
            return False
        self.done.add(key)
        pats = structures_from_findings({ch: a.payload for ch, a in arts.items()}, self.n)
        return self._post(bb, pats, [a.id for a in arts.values()])


class PriorHypothesizer(HypothesizerBase):
    """The default guess for a body nobody has described: base yaw, then mostly pitch joints."""

    source = "prior"

    def step(self, bb, t):
        if bb.epoch in self.done:
            return False
        self.done.add(bb.epoch)
        sid = self._source_id(bb, "default ranking: base yaw, then most pitch (y) joints first")
        return self._post(bb, prior_structures(self.n), [sid])


class LibraryHypothesizer(HypothesizerBase):
    """Structures of bodies seen before (transfer). Silent when the library is empty."""

    source = "library"

    def __init__(self, n, library=None, top=4):
        super().__init__(n, top)
        self.library = list(library or [])

    def step(self, bb, t):
        if not self.library or bb.epoch in self.done:
            return False
        self.done.add(bb.epoch)
        sid = self._source_id(bb, f"skill library of bodies seen before: {self.library}")
        return self._post(bb, self.library, [sid])


class LLMHypothesizer(HypothesizerBase):
    """Asks one LLM provider to read raw motions and propose structures. Calls once per epoch when
    there is data, and again (at most 3 calls per epoch) when a `hypotheses` need is open and a
    dozen new motions have arrived. Never raises: a failed call just proposes nothing."""

    MIN_DATA, NEW_DATA, MAX_CALLS = 12, 12, 3

    def __init__(self, n, provider, top=4):
        self.source = provider
        super().__init__(n, top)
        self.calls = {}                 # epoch -> list of training set sizes at each call
        self.last_why = ""

    def _prompt(self, Q, X):
        rows = "\n".join(f"q={np.round(q, 2).tolist()} -> tip_mm={np.round(x * 1000).astype(int).tolist()}"
                         for q, x in zip(Q, X))
        return (f"A jointed robot of unknown type has {self.n} unlabeled channels and we observe its "
                f"fingertip in mm (z up, base at origin). Each channel either rotates (h) or slides (s) "
                f"about or along x, y or z in the base pose frame. Propose the {self.top} most likely "
                f"structures, one token per channel such as hz or sx. Reason about which channels move "
                f"the tip in arcs versus straight lines.\n{rows}\n"
                'Answer ONLY with JSON like {"patterns": [["hz","hy","sz"]], "why": "one sentence"}')

    def _ask(self, prompt):
        if self.source == "claude":
            import anthropic
            msg = anthropic.Anthropic().messages.create(
                model=os.environ.get("BODYSCOUT_MODEL", "claude-sonnet-5-5"), max_tokens=600,
                messages=[{"role": "user", "content": prompt}])
            return msg.content[0].text
        if self.source == "gemini":
            import urllib.request
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            model = os.environ.get("BODYSCOUT_GEMINI_MODEL", "gemini-2.5-flash")
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode(),
                headers={"Content-Type": "application/json", "x-goog-api-key": key})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["candidates"][0]["content"]["parts"][0]["text"]
        raise ValueError(self.source)

    def step(self, bb, t):
        Q, X, ids = _data(bb, "train")
        calls = self.calls.setdefault(bb.epoch, [])
        if len(Q) < self.MIN_DATA or len(calls) >= self.MAX_CALLS:
            return False
        if calls and not (bb.has_need("hypotheses") and len(Q) >= calls[-1] + self.NEW_DATA):
            return False
        calls.append(len(Q))
        try:
            text = self._ask(self._prompt(Q[:24], X[:24]))
            js = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            self.last_why = js.get("why", "")
            return self._post(bb, js["patterns"], ids[:24])
        except Exception as e:  # never let an LLM take the swarm down
            self.last_why = f"{self.source} unavailable: {type(e).__name__}"
            return False


# ---------------------------------------------------------------------------
class Modeler(Agent):
    MIN_DATA = {"chain": 6, "gmm": 28, "mlp": 16}
    N_STRUCTURES = 4

    def __init__(self, family, n, seed=0, warm=None, any_types=False):
        self.family, self.n, self.seed, self.any_types = family, n, seed, any_types
        self.name = f"modeler-{family}"
        self.last_n = -1
        self.last_epoch = -1
        self.warm = warm  # parameters carried over from a previous body (transfer)

    def _structures(self, bb):
        """Up to N_STRUCTURES structures to try and the artifacts they came from. Takes each
        source's latest batch of hypotheses in SOURCE_ORDER. When no channel hypotheses exist but
        channel findings do, assembles them itself, so structure finding survives the loss of any
        or every hypothesizer."""
        batches = {}
        for h in bb.of("hypothesis"):
            if h.payload["rank"] == 0:
                batches[h.payload["source"]] = []
            batches.setdefault(h.payload["source"], []).append(h)
        cands = {src: [(h.payload["pattern"], [h.id]) for h in hs] for src, hs in batches.items()}
        if "channels" not in cands:
            arts = {a.payload["channel"]: a for a in bb.of("finding")}
            if arts:
                pats = structures_from_findings({ch: a.payload for ch, a in arts.items()}, self.n)
                cands["channels"] = [(p, [a.id for a in arts.values()]) for p in pats[: self.N_STRUCTURES]]
        rank = {s: i for i, s in enumerate(SOURCE_ORDER)}
        patterns, parents, seen = [], [], set()
        for src in sorted(cands, key=lambda s: rank.get(s, len(rank))):
            for pat, pids in cands[src]:
                if tuple(pat) not in seen and len(patterns) < self.N_STRUCTURES:
                    seen.add(tuple(pat))
                    patterns.append(pat)
                    parents += [i for i in pids if i not in parents]
        return patterns, parents

    def step(self, bb, t):
        Q, X, ids = _data(bb, "train")
        if bb.epoch != self.last_epoch:
            self.last_n, self.last_epoch = -1, bb.epoch
        if len(Q) < self.MIN_DATA[self.family] or len(Q) == self.last_n:
            return False
        kw, used = {}, []
        if self.family == "chain":
            kw["patterns"], used = self._structures(bb)
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
                                     "describe": model.describe()}, ids[-8:] + used)
        return True


# ---------------------------------------------------------------------------
def crown(bb: Blackboard) -> dict:
    """The public crowning rule, a pure function of the board that any agent can evaluate: the
    champion is the lowest error on the current holdout set among candidates that passed the replay
    check (some validator passed it, none failed it). Ties go to the older candidate. `basis` names
    every input used, so two agents that computed the same basis must name the same champion."""
    Qh, Xh, hids = _data(bb, "holdout")
    replays = {}
    for v in bb.of("verdict"):
        replays.setdefault(v.payload["candidate"], set()).add(v.payload["replayed"])
    passed = [m for m in bb.of("model") if True in replays.get(m.id, ()) and False not in replays[m.id]]
    basis = hashlib.sha1(repr(([m.id for m in passed], hids)).encode()).hexdigest()[:12]
    out = {"champion": None, "holdout_mm": None, "n_holdout": len(hids), "basis": basis}
    if len(Qh) >= 3 and passed:
        out["holdout_mm"], out["champion"] = min((m.payload["_model"].rmse(Qh, Xh) * 1000, m.id)
                                                 for m in passed)
    return out


class Validator(Agent):
    """Replay checks candidates that could win (refitting from scratch on the same data must
    reproduce the holdout score), then votes for crown(bb) every tick. A champion is posted only
    when every live validator's latest vote names the same champion. Validators announce themselves
    once with a `source` artifact; one whose latest vote is older than PATIENCE ticks is treated as
    gone. Same basis, different champion is logged as a `disagreement` and nothing is crowned."""

    PATIENCE = 2

    def __init__(self, n, goal_mm=4.0, seed=0, index=0):
        self.n, self.goal_mm, self.index = n, goal_mm, index
        self.name = f"validator-{index}"
        self.replay_seed = seed + 7777 + index  # independent replays per validator
        self.seen = set()
        self.logged = set()
        self.source_id = None

    def _replay(self, art, Q, X, Qh, Xh):
        fam = art.payload["family"]
        m = (ChainModel(self.n, restarts=3, seed=self.replay_seed) if fam == "chain"
             else FAMILIES[fam](self.n, seed=self.replay_seed))
        m.fit(Q, X, **art.payload["_fit_kw"])
        return m.rmse(Qh, Xh) * 1000

    def _judge(self, bb, Qh, Xh, hids):
        Q, X, _ = _data(bb, "train")
        best = crown(bb)
        for art in [a for a in bb.of("model") if a.id not in self.seen]:
            self.seen.add(art.id)
            score = art.payload["_model"].rmse(Qh, Xh) * 1000
            ok = None  # not checked: could not beat the current best anyway
            if best["champion"] is None or score < best["holdout_mm"]:
                k = art.payload["n_train"]  # its training set is the first k train observations
                rep = self._replay(art, Q[:k], X[:k], Qh, Xh)
                ok = bool(rep <= max(1.5 * score, score + 2.0))
            bb.post("verdict", self.name, {"candidate": art.id, "family": art.payload["family"],
                                           "holdout_mm": score, "n_holdout": len(hids),
                                           "replayed": ok}, [art.id] + hids)
            if ok:
                best = crown(bb)

    def _vote(self, bb, t):
        """Vote every tick (None until there is a candidate): the vote is also the heartbeat peers
        use to tell this validator is alive."""
        res = crown(bb)
        mine = bb.post("vote", self.name, {**res, "tick": t},
                       [res["champion"]] if res["champion"] is not None else [self.source_id])
        if res["champion"] is None:
            return
        latest = {}
        for v in bb.of("vote", epoch=-1):
            latest[v.author] = v
        peers = [a.author for a in bb.of("source", epoch=-1)
                 if a.payload["source"] == "validator" and a.author != self.name]
        backing = [mine]
        for peer in peers:
            other = latest.get(peer)
            if other is None or other.payload["tick"] < t - self.PATIENCE:
                continue  # silent for PATIENCE ticks: gone
            same_basis = other.epoch == bb.epoch and other.payload["basis"] == res["basis"]
            if other.epoch != bb.epoch or other.payload["champion"] != res["champion"]:
                if same_basis and (res["basis"], other.id) not in self.logged:
                    self.logged.add((res["basis"], other.id))
                    bb.post("disagreement", self.name, {"basis": res["basis"], "mine": res["champion"],
                                                        "theirs": other.payload["champion"]},
                            [mine.id, other.id])
                return  # same inputs, different answer: logged; otherwise it saw older inputs: wait
            backing.append(other)
        current = bb.latest("champion")
        if current is not None and current.payload["candidate"] == res["champion"]:
            return
        cand = next(a for a in bb.of("model") if a.id == res["champion"])
        bb.post("champion", self.name, {"candidate": cand.id, "family": cand.payload["family"],
                                        "_model": cand.payload["_model"], "holdout_mm": res["holdout_mm"],
                                        "n_holdout": res["n_holdout"], "describe": cand.payload["describe"],
                                        "votes": len(backing)}, [cand.id] + [v.id for v in backing])

    def step(self, bb, t):
        if self.source_id is None:  # peers count this validator from now on when deciding agreement
            self.source_id = bb.post("source", self.name, {"source": "validator",
                                                           "describes": f"{self.name} on duty"}).id
        Qh, Xh, hids = _data(bb, "holdout")
        if len(Qh) >= 3:
            self._judge(bb, Qh, Xh, hids)
        self._vote(bb, t)
        if not bb.of("observation"):
            bb.need("data", self.name, 1.0, why="no data yet")
            return True
        if len(Qh) < 3:
            bb.need("data", self.name, 1.0, why="need holdout motions")
            return False
        champ = bb.latest("champion")
        # holdout set grew since the champion was judged: re-score it honestly
        if champ is not None and current_score(bb, champ)["n_holdout"] < len(Qh):
            score = champ.payload["_model"].rmse(Qh, Xh) * 1000
            bb.post("score", self.name, {"champion": champ.id, "holdout_mm": score,
                                         "n_holdout": len(Qh)}, [champ.id] + hids)
        champ_mm = current_score(bb, champ)["holdout_mm"] if champ else None
        if champ is None:
            bb.need("data", self.name, 50.0)
        elif champ_mm > self.goal_mm:
            bb.need("data", self.name, champ_mm)
            if champ_mm > 4 * self.goal_mm and len(_data(bb, "train")[0]) >= 12:
                bb.need("hypotheses", self.name, 1.0, why="chain fits are poor, rethink structure")
        return True


# ---------------------------------------------------------------------------
class Monitor(Agent):
    """Spends one sentinel motion every `every` ticks once a champion exists. Compares the tip with
    the best body model of this epoch (the champion crowned with the lowest holdout error), not the
    latest champion: after damage the crowning rule honestly picks the least bad model on mixed
    data, and judging surprise against that would raise the bar until damage is never noticed."""

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
        champs = bb.of("champion")
        if not champs or t % self.every:
            return False
        champ = min(champs, key=lambda c: (c.payload["holdout_mm"], c.id))  # body as best known
        q = self.rng.uniform(*self.robot.limits, self.robot.n_channels)
        x = self.robot.move(q)
        pred = champ.payload["_model"].predict(q[None])[0]
        surprise = float(np.linalg.norm(pred - x)) * 1000
        thresh = max(self.k * champ.payload["holdout_mm"], self.floor)
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
