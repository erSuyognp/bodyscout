"""The swarm. Each agent owns one job, reads the blackboard, and posts artifacts. No planner, and no
single agent whose loss stops the swarm: every role has a second instance or a fallback.

Explorer x2     share the robot through needs; serve `probe` and `data` needs with motions
Channel x 2N    two per unlabeled channel, sweeping it from different base poses (home and bent); each
                wiggles only its channel, decides hinge or slide and the axis, and, when move() returns
                several fingertips, which tips that channel moves. A channel is settled only when its
                agents agree; a disputed channel gets structures with every type proposed for it
Review          when the champion stays above the goal for 3 validations in a row, asks for the least
                confident channels to be swept again from a third pose and posts that finding too
Hypothesizers   independent; each posts hypotheses tagged by source: findings (assembles channel
                findings, groups channels into limbs when there are several fingertips, and posts the
                chain `order`: which channel drives which link), prior, library, and one LLM agent per
                API key (Claude, Gemini)
Modeler x4      chain x2 (different seeds and restarts) / gmm / mlp; refit when new data lands. The chain modeler reads hypotheses, the
                limb grouping and the chain order, and works any of those out itself from channel
                findings when nobody posted one
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
from types import SimpleNamespace

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


# Every other channel's command while one channel is swept: home, bent, and the review's third pose.
# Attempt k of a sweep uses POSE_BASES[k]. Only the home sweep reports its axis in the base frame.
POSE_BASES = (0.0, 0.8, -0.8)
SLIDE_RATIO = 0.12   # second over first singular value of a sweep: below this the path is a line


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
        preds = np.stack([m.predict(cands) for m in models])          # (k, C, 3) or (k, C, tips, 3)
        dev = preds.std(0)
        disagree = np.linalg.norm(dev, axis=1) if dev.ndim == 2 else np.linalg.norm(dev, axis=-1).mean(-1)
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
        base = np.full(n, POSE_BASES[attempt])
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
def _classify_one(P, attempt):
    """One fingertip's sweep. Returns (fields or None, spread in metres)."""
    _, sv, vt = np.linalg.svd(P - P.mean(0))
    spread = float(sv[0])
    if spread < 0.006:
        return None, spread
    ratio = float(sv[1] / sv[0])
    kind = "s" if ratio < SLIDE_RATIO else "h"
    direction = vt[0] if kind == "s" else vt[2]
    axis = "xyz"[int(np.argmax(np.abs(direction)))]
    conf = float(np.max(np.abs(direction))) if attempt == 0 else 0.0  # bent pose: frame differs
    margin = min(1.0, abs(np.log(max(ratio, 1e-6) / SLIDE_RATIO)) / np.log(4.0))  # how clear hinge vs slide is
    return {"type": kind, "axis": axis, "conf": conf, "curvature": ratio, "type_margin": float(margin),
            "spread_mm": spread * 1000}, spread


def classify_sweep(P, attempt):
    """The channel rule, as a pure function of one channel's sweep (one row per probe value).

    P is (samples, 3) for one marker, or (samples, n_tips, 3) when move() returns every fingertip.
    A tip counts as moved when its path is large beside the tip that moved most, so a shared base
    joint lists every fingertip and a limb joint lists only its own. Returns (finding fields, spread
    in m); fields is None when no tip really moved. A single-marker sweep returns the same fields as
    before, with no `tips` key.
    """
    P = np.asarray(P, float)
    if P.ndim == 2:
        return _classify_one(P, attempt)
    per = [_classify_one(P[:, t], attempt) for t in range(P.shape[1])]
    moving = [(t, f, s) for t, (f, s) in enumerate(per) if f is not None]
    if not moving:
        return None, max(s for _, s in per)
    _, best, biggest = max(moving, key=lambda row: row[2])
    keep = [t for t, _, s in moving if s >= max(0.006, 0.25 * biggest)]
    fields = dict(best)
    fields["tips"] = sorted(keep)
    if any(per[t][0]["type"] != fields["type"] for t in keep):
        fields["conf"] = 0.0
    return fields, biggest


def probe_need_kind(ch, attempt):
    """One need kind per (channel, pose), so two agents asking for the same sweep share it."""
    return f"probe:{ch}" if attempt == 0 else f"probe:{ch}:{attempt}"


class ChannelAgent(Agent):
    """Owns one unlabeled channel. Asks for a sweep of only that channel, then reads the shape of
    the fingertip path: a straight line means the joint slides, an arc means it rotates. The line
    direction (slide) or the arc's plane normal (hinge) gives the axis. When the robot reports
    several fingertips, the finding also lists which tips this channel moved. Knows nothing about
    other channels; hypothesizers and the chain modeler assemble everyone's findings into limbs.

    poses: the sweep poses to try in order (indices into POSE_BASES), moving on when the tip barely
    moved. The home agent tries (0, 1); its replica, which sweeps from the bent pose, tries (1, 2)."""

    def __init__(self, channel, n, poses=(0, 1), name=None):
        self.ch, self.n, self.poses = channel, n, tuple(poses)
        self.name = name or f"channel-{channel}"
        self.pressure = (200.0 if self.poses[0] == 0 else 150.0) - channel  # home sweeps first
        self.epoch, self.k, self.requested, self.done = -1, 0, False, False

    @property
    def attempt(self):
        return self.poses[self.k]

    def step(self, bb, t):
        if bb.epoch != self.epoch:
            self.epoch, self.k, self.requested, self.done = bb.epoch, 0, False, False
        if self.done:
            return False
        obs = [a for a in bb.of("observation")
               if a.payload.get("probe") == self.ch and a.payload.get("attempt") == self.attempt]
        if len(obs) < len(Explorer.PROBE_VALUES):
            if not self.requested:
                bb.need(probe_need_kind(self.ch, self.attempt), self.name, self.pressure, channel=self.ch,
                        attempt=self.attempt)
                self.requested = True
            return False
        obs = obs[: len(Explorer.PROBE_VALUES)]
        fields, spread = classify_sweep(np.array([a.payload["x"] for a in obs]), self.attempt)
        if fields is None:  # the tip barely moved from this pose: look again from the next one
            if self.k + 1 < len(self.poses):
                self.k, self.requested = self.k + 1, False
                return True
            bb.post("finding", self.name, {"channel": self.ch, "type": "?", "axis": "?", "conf": 0.0,
                                           "spread_mm": spread * 1000, "attempt": self.attempt},
                    [a.id for a in obs])
            self.done = True
            return True
        bb.post("finding", self.name, {"channel": self.ch, **fields, "attempt": self.attempt}, [a.id for a in obs])
        self.done = True
        return True


def merge_findings(arts) -> dict:
    """Every finding about one channel, as one payload. The primary opinion is a home pose sweep when
    there is one (it alone reports the axis in the base frame), else the first with a type. When the
    opinions name different joint types, `disputed` lists the other types, so structures get built
    with each. `_ids` keeps every finding for provenance; `type_margin` is the least clear opinion."""
    known = [a for a in arts if a.payload["type"] != "?"]
    if not known:
        a = arts[-1]
        return {**a.payload, "_id": a.id, "_ids": [x.id for x in arts], "type_margin": 0.0}
    home = [a for a in known if a.payload.get("attempt", 0) == 0]
    primary = max(home, key=lambda a: (a.payload["conf"], -a.id)) if home else known[0]
    out = {**primary.payload, "_id": primary.id, "_ids": [x.id for x in arts],
           "type_margin": min(a.payload.get("type_margin", 1.0) for a in known)}
    others = sorted({a.payload["type"] for a in known} - {primary.payload["type"]})
    if others:
        out["disputed"] = others
        out["type_margin"] = 0.0
    return out


def channel_findings(bb) -> dict:
    """{channel: merged finding} for this epoch, from however many agents reported on each channel."""
    by = {}
    for a in bb.of("finding"):
        by.setdefault(a.payload["channel"], []).append(a)
    return {ch: merge_findings(arts) for ch, arts in by.items()}


def finding_ids(findings: dict) -> list:
    return [i for f in findings.values() for i in f.get("_ids", [f["_id"]])]


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
        elif f.get("disputed"):  # agents disagree on the type: every type with the measured axis first
            types = [f["type"]] + list(f["disputed"])
            opts.append([(t + f["axis"], 0) for t in types] + [(t + a, 1) for t in types for a in "zyx" if a != f["axis"]])
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


# ---------------------------------------------------------------------------
# Chain order. Nothing says channel 0 drives the base. Each channel sweep from the home pose traces
# that joint's axis line (hinge: arc normal and centre; slide: line direction), and those lines do not
# depend on the order. Given them, any order predicts every tip with no fitting (product of
# exponentials: apply the most distal joint first), so the order is a search over permutations scored
# on the motions where several channels moved at once.

ORDER_MAX_N = 8      # 8! = 40320 orders; past that the exhaustive search is too slow
ORDER_EVERY = 8      # recompute the order each time this many more mixed motions arrive


def _spin(r, w, a):
    """Rotate vectors r (M,3) about unit axis w by angles a (M,)."""
    c, s = np.cos(a)[:, None], np.sin(a)[:, None]
    return r * c + np.cross(w, r) * s + np.outer(r @ w, w) * (1 - c)


def _move_point(g, p, v):
    """Apply one joint's home pose screw g to points p (M,3) at commands v (M,)."""
    if g is None:
        return p
    if g[0] == "h":
        return g[2] + _spin(p - g[2], g[1], v)
    return p + v[:, None] * g[1]


def _sweep_geometry(kind, v, P):
    """One channel's screw from its home pose sweep, plus its estimate of the home tip."""
    if kind == "s":
        coef = np.linalg.lstsq(np.c_[v, np.ones_like(v)], P, rcond=None)[0]
        return ("s", coef[0]), coef[1]
    m = P.mean(0)
    _, _, vt = np.linalg.svd(P - m)
    u = (P - m) @ vt[:2].T                                  # arc in its own plane
    a, b, _ = np.linalg.lstsq(np.c_[2 * u, np.ones(len(u))], (u ** 2).sum(1), rcond=None)[0]
    c = m + a * vt[0] + b * vt[1]                           # circle centre (Kasa fit)
    best = None
    for w in (vt[2], -vt[2]):                               # which way positive commands turn
        homes = _move_point(("h", w, c), P, -v)
        spread = float(homes.std(0).sum())
        if best is None or spread < best[0]:
            best = (spread, ("h", w, c), homes.mean(0))
    return best[1], best[2]


def _refine(geo, home, sweeps):
    """Joint least squares over every sweep with one shared home tip."""
    from scipy.optimize import least_squares
    chans = [ch for ch in sorted(sweeps) if geo[ch] is not None]

    def unpack(p):
        out, k = {}, 3
        for ch in chans:
            if geo[ch][0] == "h":
                w = p[k:k + 3]
                out[ch] = ("h", w / (np.linalg.norm(w) + 1e-12), p[k + 3:k + 6])
                k += 6
            else:
                out[ch] = ("s", p[k:k + 3])
                k += 3
        return p[:3], out

    def res(p):
        x0, g = unpack(p)
        r = [(_move_point(g[ch], np.tile(x0, (len(sweeps[ch][0]), 1)), sweeps[ch][0]) - sweeps[ch][1]).ravel()
             for ch in chans]
        for ch in chans:  # the centre may slide along its own axis for free: pin it lightly
            if g[ch][0] == "h":
                r.append([1e-2 * (g[ch][2] - geo[ch][2]) @ g[ch][1]])
        return np.concatenate(r)

    p0 = np.concatenate([home] + [np.r_[g[1], g[2]] if g[0] == "h" else g[1] for g in (geo[ch] for ch in chans)])
    x0, g = unpack(least_squares(res, p0, method="trf", max_nfev=200).x)
    return x0, {ch: g.get(ch) for ch in geo}


def infer_order(findings: dict, obs: list, n: int):
    """Most likely chain order (channel driving each link, base first) from the channel sweeps and
    the motions seen so far. Returns (order, info) or None when there is not enough to go on.
    When channels in their given order explain the data about as well, keeps that order.
    One fingertip only: several tips are a tree, and resolve_limbs orders each limb instead."""
    if len(findings) < n or n > ORDER_MAX_N:
        return None
    if obs and np.asarray(obs[0].payload["x"]).ndim != 1:
        return None
    train = [a for a in obs if a.payload["split"] == "train"]
    mixed = [a for a in train if "probe" not in a.payload]
    if len(mixed) < max(8, n):
        return None
    sweeps, geo, homes = {}, {}, []
    for ch in range(n):
        pts = [a for a in train if a.payload.get("probe") == ch and a.payload.get("attempt") == 0]
        kind = findings[ch]["type"]
        if len(pts) < 3 or kind == "?":
            geo[ch] = None  # never seen to move the tip from home: treated as moving nothing
            continue
        v = np.array([a.payload["q"][ch] for a in pts])
        P = np.array([a.payload["x"] for a in pts])
        sweeps[ch] = (v, P)
        geo[ch], h = _sweep_geometry(kind, v, P)
        homes.append(h)
    if not homes:
        return None
    x0, geo = _refine(geo, np.median(homes, axis=0), sweeps)
    Q = np.array([a.payload["q"] for a in train])
    X = np.array([a.payload["x"] for a in train])
    scores = {}

    def search(p, left, suffix):  # suffix: the distal end of the chain, already applied to p
        if not left:
            scores[tuple(suffix)] = float(np.sqrt(np.mean(np.sum((p - X) ** 2, axis=1))))
            return
        for ch in left:
            search(_move_point(geo[ch], p, Q[:, ch]), [c for c in left if c != ch], [ch] + suffix)

    search(np.tile(x0, (len(Q), 1)), list(range(n)), [])
    best = min(scores.values())
    ident = scores[tuple(range(n))]
    if ident <= 1.2 * best + 0.002:
        order = list(range(n))
    else:  # orders that fit equally well (commuting joints): take the one closest to as wired
        ties = [o for o, s in scores.items() if s <= 1.05 * best + 5e-4]
        order = list(min(ties, key=lambda o: (sum(a > b for i, a in enumerate(o) for b in o[i + 1:]), o)))
    return order, {"rmse_mm": best * 1000, "as_wired_rmse_mm": ident * 1000, "n_motions": len(mixed),
                   "parents": [findings[ch]["_id"] for ch in range(n)] + [a.id for a in mixed[-8:]]}


def order_key(bb):
    """(epoch, data bucket): when the chain order is worth recomputing."""
    mixed = sum(1 for a in bb.of("observation") if a.payload["split"] == "train" and "probe" not in a.payload)
    return bb.epoch, mixed // ORDER_EVERY


def order_from_board(bb, n):
    """Chain order from the merged findings. A disputed channel's sweep geometry depends on its type,
    so every combination of the disputed types is tried and the best fitting order kept."""
    merged = channel_findings(bb)
    disputed = sorted(ch for ch, f in merged.items() if f.get("disputed"))
    best = None
    for combo in itertools.product(*[[merged[ch]["type"]] + merged[ch]["disputed"] for ch in disputed]):
        fs = dict(merged)
        for ch, ty in zip(disputed, combo):
            fs[ch] = {**merged[ch], "type": ty}
        found = infer_order(fs, bb.of("observation"), n)
        if found is not None and (best is None or found[1]["rmse_mm"] < best[1]["rmse_mm"]):
            best = found
    return best


def limb_groups(findings: dict, n: int):
    """Channels of each fingertip, shared (moves more than one tip) first.

    None when every channel affects only the single marker, which keeps the serial chain.
    """
    if any(ch not in findings for ch in range(n)):
        return None
    tips = []
    for ch in range(n):
        f = findings[ch]
        if f.get("type") == "?":
            tips.append(())
        else:
            tips.append(tuple(int(t) for t in f.get("tips", (0,))))
    known = [t for t in tips if t]
    if not known or (max(max(t) for t in known) == 0 and all(len(t) <= 1 for t in tips)):
        return None
    n_tips = 1 + max(max(t) for t in known)
    shared = [ch for ch, t in enumerate(tips) if len(t) > 1]
    return [shared + [ch for ch, t in enumerate(tips) if t == (tip,)] for tip in range(n_tips)]


def _order_subset(findings, obs, channels, tip):
    """Chain order of `channels` using only fingertip `tip`. None without enough mixed motions."""
    if len(channels) <= 1:
        return list(channels), {}
    index = {c: i for i, c in enumerate(channels)}
    sub = {}
    for c in channels:
        f = dict(findings[c])
        f["channel"] = index[c]
        f.setdefault("_id", 0)
        sub[index[c]] = f
    reduced = []
    for a in obs:
        payload = dict(a.payload)
        x = np.asarray(payload["x"])
        if x.ndim != 1:
            payload["x"] = np.asarray(x[tip], float)
        q = np.asarray(payload["q"], float)
        payload["q"] = np.array([q[c] for c in channels])
        probe = payload.get("probe")
        if probe is not None and probe not in index:
            continue
        if probe is not None:
            payload["probe"] = index[probe]
        reduced.append(SimpleNamespace(id=getattr(a, "id", 0), payload=payload))
    found = infer_order(sub, reduced, len(channels))
    if found is None:
        return None
    order, info = found
    return [channels[i] for i in order], info


def resolve_limbs(findings: dict, obs: list, n: int):
    """One ordered chain per fingertip, trunk channels first. None for a single marker.

    Membership comes from which tip each channel moved. Order inside a limb is the product-of-
    exponentials search when enough mixed motions exist, otherwise channel order (trunk, then the
    limb). Shared joints stay a prefix: they are proximal to the branch.
    """
    groups = limb_groups(findings, n)
    if groups is None:
        return None
    shared = [ch for ch in range(n)
              if findings[ch].get("type") != "?" and len(tuple(findings[ch].get("tips", (0,)))) > 1]
    shared_set = set(shared)
    refined, shared_orders = [], []
    for tip, members in enumerate(groups):
        found = _order_subset(findings, obs, members, tip)
        if found is None:
            refined.append(list(members))
            continue
        order, info = found
        shared_part = [c for c in order if c in shared_set]
        private_part = [c for c in order if c not in shared_set]
        refined.append(shared_part + private_part)
        shared_orders.append((info.get("rmse_mm", 0.0), shared_part))
    if shared_orders and any(part for _, part in shared_orders):
        best_shared = min(shared_orders, key=lambda item: item[0])[1]
        if best_shared:
            return [list(best_shared) + [c for c in limb if c not in set(best_shared)] for limb in refined]
    return refined


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

    def _post(self, bb, patterns, parents, **extra):
        seen, n_posted = set(), 0
        for p in patterns:
            p = [_tok(c) for c in p]
            if len(p) != self.n or tuple(p) in seen:
                continue
            seen.add(tuple(p))
            bb.post("hypothesis", self.name, {"pattern": p, "source": self.source, "rank": n_posted, **extra},
                    parents)
            n_posted += 1
            if n_posted == self.top:
                break
        return n_posted > 0


class FindingsHypothesizer(HypothesizerBase):
    """Assembles the channel agents' findings into whole body structures, groups channels into
    limbs when several fingertips are observed (`limbs` artifacts), and works out which channel
    drives which link (`order` artifacts) as mixed motions come in."""

    source = "channels"

    def _order(self, bb):
        arts = channel_findings(bb)
        if limb_groups(arts, self.n) is not None:
            return False  # several fingertips: the limbs artifact carries each chain's order
        key = ("order",) + order_key(bb)
        if key in self.done:
            return False
        found = order_from_board(bb, self.n)
        if found is None:
            return False
        self.done.add(key)
        order, info = found
        bb.post("order", self.name, {"order": order, **{k: v for k, v in info.items() if k != "parents"}},
                info["parents"])
        return True

    def _limbs(self, bb):
        """Group channels by the fingertip they move, and post that grouping once it changes."""
        findings = channel_findings(bb)
        if len(findings) < self.n:
            return False
        if limb_groups(findings, self.n) is None:
            return False
        key = ("limbs",) + order_key(bb)
        if key in self.done:
            return False
        limbs = resolve_limbs(findings, bb.of("observation"), self.n)
        self.done.add(key)
        if limbs is None:
            return False
        prev = bb.latest("limbs")
        if prev is not None and prev.payload["limbs"] == limbs:
            return False
        bb.post("limbs", self.name, {"limbs": limbs}, finding_ids(findings))
        return True

    def step(self, bb, t):
        if self._assemble(bb):
            return True
        if len(channel_findings(bb)) < self.n:
            return False
        return self._limbs(bb) or self._order(bb)

    def _assemble(self, bb):
        arts = channel_findings(bb)
        if not arts:
            return False
        if len(arts) < self.n and not bb.has_need("hypotheses"):
            return False  # waits for channel agents, never for another hypothesizer
        ids = finding_ids(arts)
        key = (bb.epoch, tuple(sorted(ids)))
        if key in self.done:
            return False
        self.done.add(key)
        return self._post(bb, structures_from_findings(arts, self.n), ids)


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
    """Asks one LLM provider to propose structures from the channel agents' findings plus raw motions.
    Calls once per epoch, as soon as every channel has a finding, or once the epoch has 8 train
    motions and no channel is still being probed. The answer (or the failure) is cached for the
    epoch. Never raises: a failed call just proposes nothing, and the other hypothesizers carry on."""

    MIN_DATA, MAX_ROWS, TIMEOUT_S = 8, 24, 20.0

    def __init__(self, n, provider, top=4):
        self.source = provider
        super().__init__(n, top)
        self.answers = {}               # epoch -> (patterns, why), or None when the call failed
        self.last_why = ""

    def _prompt(self, findings, Q, X):
        def _fact(ch, f):
            tips = f" tips={list(f['tips'])}" if "tips" in f else ""
            curv = f.get("curvature", float("nan"))
            return (f"channel {ch}: type={f['type']} axis={f['axis']} curvature={curv:.3f} "
                    f"spread_mm={f['spread_mm']:.1f}{tips}")

        facts = "\n".join(_fact(ch, f) for ch, f in sorted(findings.items())) or "none yet"
        rows = "\n".join(f"q={np.round(q, 2).tolist()} -> tip_mm={np.round(x * 1000).astype(int).tolist()}"
                         for q, x in zip(Q, X)) or "none yet"
        return (f"A jointed robot of unknown type has {self.n} unlabeled channels and we observe its "
                f"fingertip in mm (z up, base at origin). Each channel either rotates (h) or slides (s) "
                f"about or along x, y or z in the base pose frame. Propose the {self.top} most likely "
                f"structures, one token per channel such as hz or sx.\n"
                f"Per channel findings from sweeping one channel at a time (type h = arc, s = straight "
                f"line, ? = tip barely moved; axis = arc normal or line direction; curvature = second over "
                f"first singular value of the tip path, near 0 for a line; spread_mm = size of the path):\n"
                f"{facts}\nRaw motions:\n{rows}\n"
                'Answer ONLY with JSON like {"patterns": [["hz","hy","sz"]], "why": "one sentence"}')

    def _ask(self, prompt):
        if self.source == "claude":
            import anthropic
            client = anthropic.Anthropic(timeout=self.TIMEOUT_S, max_retries=0)
            msg = client.messages.create(
                model=os.environ.get("BODYSCOUT_MODEL") or "claude-sonnet-5-5", max_tokens=4000,
                output_config={"effort": "low"},  # keeps the answer inside the 20 second timeout
                messages=[{"role": "user", "content": prompt}])
            if msg.stop_reason == "refusal":
                raise RuntimeError("refusal")
            return next(b.text for b in msg.content if b.type == "text")
        if self.source == "gemini":
            import urllib.request
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            model = os.environ.get("BODYSCOUT_GEMINI_MODEL", "gemini-2.5-flash")
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode(),
                headers={"Content-Type": "application/json", "x-goog-api-key": key})
            with urllib.request.urlopen(req, timeout=self.TIMEOUT_S) as r:
                return json.load(r)["candidates"][0]["content"]["parts"][0]["text"]
        raise ValueError(self.source)

    def _ready(self, bb, findings, n_train):
        """Every channel has a finding, or 8 train motions with no channel sweep waiting: either no
        channel agents exist (a known arm), or someone needs hypotheses (channel agents lost)."""
        if len(findings) == self.n:
            return True
        if n_train < self.MIN_DATA or any(nd.open and nd.kind.startswith("probe:") for nd in bb.needs):
            return False
        return bb.has_need("hypotheses") or not any("probe" in a.payload for a in bb.of("observation"))

    def step(self, bb, t):
        if bb.epoch in self.answers:
            return False
        arts = channel_findings(bb)
        Q, X, ids = _data(bb, "train")
        if not self._ready(bb, arts, len(Q)):
            return False
        try:
            text = self._ask(self._prompt(arts, Q[: self.MAX_ROWS], X[: self.MAX_ROWS]))
            js = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            self.answers[bb.epoch] = (js["patterns"], str(js.get("why", "")))
        except Exception as e:  # never let an LLM take the swarm down
            self.answers[bb.epoch] = None
            self.last_why = f"{self.source} unavailable: {type(e).__name__}"
            return False
        pats, self.last_why = self.answers[bb.epoch]
        parents = finding_ids(arts) + ids[: self.MAX_ROWS]
        return self._post(bb, pats, parents, why=self.last_why)


# ---------------------------------------------------------------------------
class Modeler(Agent):
    MIN_DATA = {"chain": 6, "gmm": 28, "mlp": 16}
    N_STRUCTURES = 4

    def __init__(self, family, n, seed=0, warm=None, any_types=False, index=0, restarts=3):
        self.family, self.n, self.seed, self.any_types = family, n, seed, any_types
        self.restarts = restarts
        self.name = f"modeler-{family}" + (f"-{index}" if index else "")
        self.last_n = -1
        self.last_epoch = -1
        self.warm = warm  # parameters carried over from a previous body (transfer)
        self.own_order = {}  # order_key -> order, worked out here when nobody posted one
        self.own_limbs = {}  # order_key -> limb chains, worked out here when nobody posted one

    def _order(self, bb):
        """Latest posted chain order this epoch; with none, work it out from the findings itself,
        so a lost findings hypothesizer does not leave the channels in the wrong order."""
        posted = bb.latest("order")
        if posted is not None:
            return posted.payload["order"], [posted.id]
        if not bb.of("finding"):
            return None, []
        key = order_key(bb)
        if key not in self.own_order:
            found = order_from_board(bb, self.n)
            self.own_order[key] = found[0] if found else None
        return self.own_order[key], []

    def _limbs(self, bb):
        """Latest limb grouping this epoch; with none posted, group the channel findings itself."""
        posted = bb.latest("limbs")
        if posted is not None:
            return posted.payload["limbs"], [posted.id]
        findings = channel_findings(bb)
        if len(findings) < self.n:
            return None, []
        key = order_key(bb)
        if key not in self.own_limbs:
            self.own_limbs[key] = resolve_limbs(findings, bb.of("observation"), self.n)
        return self.own_limbs[key], []

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
            arts = channel_findings(bb)
            if arts:
                pats = structures_from_findings(arts, self.n)
                cands["channels"] = [(p, finding_ids(arts)) for p in pats[: self.N_STRUCTURES]]
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
        # A multi-tip chain is not worth fitting until the channel sweeps finish: the limb grouping
        # is what makes the tree, and a blind topology search would throw those motions away.
        if (self.family == "chain" and np.asarray(X).ndim == 3
                and any(nd.open and nd.kind.startswith("probe:") for nd in bb.needs)):
            return False
        kw, used = {}, []
        if self.family == "chain":
            kw["patterns"], used = self._structures(bb)
            limbs, lids = self._limbs(bb)
            if limbs is not None:
                kw["limbs"] = limbs  # several fingertips: each chain's order is inside the grouping
                used = used + lids
            else:
                order, oids = self._order(bb)
                if order is not None and order != list(range(self.n)):
                    kw["order"] = order
                    used = used + oids
            prev = [a for a in bb.of("champion", epoch=-1) if a.payload["family"] == "chain"]
            kw["warm"] = prev[-1].payload["_model"].warm_state if prev else self.warm
            model = ChainModel(self.n, restarts=self.restarts, seed=self.seed + len(Q), any_types=self.any_types)
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
NEAR_TIE = 1.05      # crown: a candidate within 5% (+0.05 mm) of the best counts as tied


def crown(bb: Blackboard) -> dict:
    """The public crowning rule, a pure function of the board that any agent can evaluate: the
    champion is the lowest error on the current holdout set among candidates that passed the replay
    check (some validator passed it, none failed it). Ties, and near ties within NEAR_TIE, go to the
    older candidate. `basis` names
    every input used, so two agents that computed the same basis must name the same champion."""
    Qh, Xh, hids = _data(bb, "holdout")
    replays = {}
    for v in bb.of("verdict"):
        replays.setdefault(v.payload["candidate"], set()).add(v.payload["replayed"])
    passed = [m for m in bb.of("model") if True in replays.get(m.id, ()) and False not in replays[m.id]]
    basis = hashlib.sha1(repr(([m.id for m in passed], hids)).encode()).hexdigest()[:12]
    out = {"champion": None, "holdout_mm": None, "n_holdout": len(hids), "basis": basis}
    if len(Qh) >= 3 and passed:
        scored = [(m.payload["_model"].rmse(Qh, Xh) * 1000, m.id) for m in passed]
        best = min(mm for mm, _ in scored)
        # near ties go to the older candidate too: two chain modelers post near copies every tick,
        # and a winner that flips on a hair would keep the validators from ever agreeing
        out["holdout_mm"], out["champion"] = min((s for s in scored if s[0] <= best * NEAR_TIE + 0.05),
                                                 key=lambda s: s[1])
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
        """Holdout error of a refit from scratch, or None when the refit itself fails (a numerical
        failure must fail the check, never take the validator, and with it the run, down)."""
        fam = art.payload["family"]
        m = (ChainModel(self.n, restarts=3, seed=self.replay_seed) if fam == "chain"
             else FAMILIES[fam](self.n, seed=self.replay_seed))
        try:
            m.fit(Q, X, **art.payload["_fit_kw"])
            return m.rmse(Qh, Xh) * 1000
        except Exception:
            return None

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
                ok = rep is not None and bool(rep <= max(1.5 * score, score + 2.0))
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
class ReviewAgent(Agent):
    """Questions the channel findings when the model built on them stays bad. A validation is a new
    (champion, holdout size) score. After STRIKES validations in a row above the goal, asks for the
    RECHECK least confident channels (disputed first, then the least clear hinge or slide call) to be
    swept again from the third pose, reads each sweep with the channel rule and posts it as one more
    finding. A recheck that disagrees makes the channel disputed, so the hypothesizers propose every
    type and the validators decide on held out error. Each channel is rechecked at most once an epoch."""

    name = "review"
    STRIKES, RECHECK, POSE = 3, 2, 2

    def __init__(self, n, goal_mm=4.0):
        self.n, self.goal = n, goal_mm
        self.epoch = -1

    def _reset(self, bb):
        self.epoch, self.scores, self.pending, self.checked = bb.epoch, {}, {}, set()

    def _read_sweeps(self, bb):
        posted = False
        for ch, need_id in list(self.pending.items()):
            obs = [a for a in bb.of("observation")
                   if a.payload.get("probe") == ch and a.payload.get("attempt") == self.POSE]
            if len(obs) < len(Explorer.PROBE_VALUES):
                continue
            obs = obs[: len(Explorer.PROBE_VALUES)]
            fields, spread = classify_sweep(np.array([a.payload["x"] for a in obs]), self.POSE)
            if fields is None:
                fields = {"type": "?", "axis": "?", "conf": 0.0, "spread_mm": spread * 1000}
            bb.post("finding", self.name, {"channel": ch, **fields, "attempt": self.POSE, "recheck": True},
                    [a.id for a in obs] + [need_id])
            del self.pending[ch]
            posted = True
        return posted

    def step(self, bb, t):
        if bb.epoch != self.epoch:
            self._reset(bb)
        posted = self._read_sweeps(bb)
        champ = bb.latest("champion")
        if champ is None or self.pending:
            return posted
        s = current_score(bb, champ)
        self.scores.setdefault((champ.id, s["n_holdout"]), (s["holdout_mm"], champ.id))
        last = list(self.scores.values())[-self.STRIKES:]
        if len(last) < self.STRIKES or min(mm for mm, _ in last) <= self.goal:
            return posted
        findings = channel_findings(bb)
        cands = sorted((f.get("type_margin", 1.0), ch) for ch, f in findings.items() if ch not in self.checked)
        for _, ch in cands[: self.RECHECK]:
            need = bb.need(probe_need_kind(ch, self.POSE), self.name, 120.0 - ch,
                           parents=[cid for _, cid in last] + findings[ch].get("_ids", [findings[ch]["_id"]]),
                           channel=ch, attempt=self.POSE, why="champion above goal: recheck this channel")
            self.pending[ch] = need.id
            self.checked.add(ch)
        self.scores = {}  # the next recheck needs fresh strikes
        return bool(cands) or posted


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
