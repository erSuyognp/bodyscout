"""Fault injection for experiments, applied the same way to every condition.

This module is part of the hidden world, like world.py: it may read `robot.spec` to make a fault
wrong on purpose (a bad source must propose structures that are really wrong). No agent imports it
or reads its fields; `swarm.run` wires each fault into whatever slot a condition has for it.

  wrong_finding  one channel's joint type is reported flipped (hinge <-> slide), confidence unchanged
  bad_llm        a hypothesis source posts 3 confident wrong structures every epoch, in an LLM's slot
  modeler_crash  the chain modeler stops producing models from motion CRASH_AT on
  noisy_channel  the sweep observations of one channel get NOISY_MM of extra noise (std per axis)

Faults hit one agent instance, not a role: wrong_finding corrupts the faulty channel's home pose agent
(`channel-<k>`; the swarm's bent pose replica `channel-bent-<k>` and the review's recheck report what
they measure), and modeler_crash kills `modeler-chain` (the swarm's second chain modeler,
`modeler-chain-1`, keeps running). Conditions with one instance lose that instance: the pipeline's
channel stage and modeler, the single agents' own probing and fitting. noisy_channel is in the
camera, so it corrupts every sweep of that channel from any pose, whoever asked for it.

The faulty channel is `seed % n_channels`, so each robot gets one fixed channel. A condition with no
slot for a fault (a single agent has no channel findings and no hypothesis source) runs unchanged;
`Faults.hits` counts how often a fault actually fired, so results can say where it did not apply.
"""
from __future__ import annotations

import numpy as np

FAULTS = ("none", "wrong_finding", "bad_llm", "modeler_crash", "noisy_channel")
CRASH_AT = 24
NOISY_MM = 20.0
PROBE_VALUES = (-1.5, -0.5, 0.5, 1.5)   # same as Explorer.PROBE_VALUES; kept here so agents stay unaware
PROBE_BASES = (0.0, 0.8, -0.8)          # home, bent and recheck poses (agents.POSE_BASES)


def _flip(token: str) -> str:
    return ("s" if token[0] == "h" else "h") + token[1:]


class Faults:
    def __init__(self, kinds, robot, seed=0):
        kinds = [kinds] if isinstance(kinds, str) else list(kinds or [])
        kinds = [k for k in kinds if k != "none"]
        bad = set(kinds) - set(FAULTS)
        if bad:
            raise ValueError(f"unknown faults {sorted(bad)}; known: {FAULTS}")
        self.kinds = set(kinds)
        self.n = robot.n_channels
        self.channel = seed % self.n
        self.seed = seed
        self.hits = {k: 0 for k in self.kinds}
        self._truth = list(robot.spec.tokens()) if "bad_llm" in self.kinds else None

    def __contains__(self, kind):
        return kind in self.kinds

    def hit(self, kind, k=1):
        self.hits[kind] = self.hits.get(kind, 0) + k

    # wrong_finding -----------------------------------------------------------------------
    def finding(self, ch, fields: dict) -> dict:
        """The finding as reported: the faulty channel's type flipped, everything else as measured."""
        if "wrong_finding" not in self.kinds or ch != self.channel or fields.get("type") not in ("h", "s"):
            return fields
        self.hit("wrong_finding")
        return {**fields, "type": "s" if fields["type"] == "h" else "h"}

    # bad_llm -----------------------------------------------------------------------------
    def wrong_structures(self, k=3) -> list:
        """k distinct structures, each one token away from the hidden body: a confident near miss."""
        truth, n, out = self._truth, self.n, []
        for j in range(n):
            ch = (self.channel + j) % n
            for tok in (_flip(truth[ch]),) + tuple(truth[ch][0] + a for a in "zyx" if a != truth[ch][1]):
                cand = truth[:ch] + [tok] + truth[ch + 1:]
                if cand != truth and cand not in out:
                    out.append(cand)
                    break
            if len(out) == k:
                break
        return out

    # modeler_crash -----------------------------------------------------------------------
    def crashed(self, motions: int) -> bool:
        return "modeler_crash" in self.kinds and motions >= CRASH_AT

    # noisy_channel -----------------------------------------------------------------------
    def wrap(self, robot):
        return NoisyChannelRobot(robot, self, self.channel, NOISY_MM / 1000, self.seed) \
            if "noisy_channel" in self.kinds else robot


def is_probe_of(q, ch) -> bool:
    """q is a sweep of channel ch: every other channel at one base pose, ch at a probe value."""
    q = np.asarray(q, float)
    rest = np.delete(q, ch)
    return (len(rest) > 0 and bool(np.all(rest == rest[0])) and float(rest[0]) in PROBE_BASES
            and float(q[ch]) in PROBE_VALUES)


class NoisyChannelRobot:
    """The robot as the agents see it, with a bad camera on one channel's sweeps. Everything else
    (scoring, damage, motion count) passes through to the real robot."""

    def __init__(self, robot, faults, channel, sigma, seed):
        self._robot, self._faults, self._ch, self._sigma = robot, faults, channel, sigma
        self._rng = np.random.default_rng(seed + 4242)

    def __getattr__(self, name):
        return getattr(self._robot, name)

    def move(self, q):
        x = self._robot.move(q)
        if is_probe_of(np.clip(np.asarray(q, float), *self._robot.limits), self._ch):
            self._faults.hit("noisy_channel")
            x = x + self._rng.normal(0.0, self._sigma, np.shape(x))
        return x


# ---- swarm side: the same faults, posted onto the blackboard -----------------------------
from .agents import HypothesizerBase  # noqa: E402  (agents never import this module)


class _FlippedBoard:
    """The blackboard as one channel agent writes to it: its finding goes through Faults.finding."""

    def __init__(self, bb, faults):
        self._bb, self._faults = bb, faults

    def __getattr__(self, name):
        return getattr(self._bb, name)

    def post(self, kind, author, payload, parents=None):
        if kind == "finding":
            payload = self._faults.finding(payload["channel"], payload)
        return self._bb.post(kind, author, payload, parents)


class FlippedChannelAgent:
    """Wraps the faulty channel's agent: it measures as usual and reports its type flipped."""

    def __init__(self, agent, faults):
        self.agent, self.faults, self.name = agent, faults, agent.name

    def step(self, bb, t):
        return self.agent.step(_FlippedBoard(bb, self.faults), t)


class WrongHypothesizer(HypothesizerBase):
    """bad_llm: sits in an LLM's slot (source "claude") and posts 3 confident wrong structures at the
    start of every epoch. Its hypotheses carry fault="bad_llm" so provenance can name it; no agent
    reads that field."""

    source = "claude"

    def __init__(self, n, faults):
        super().__init__(n, top=3)
        self.faults = faults

    def step(self, bb, t):
        if bb.epoch in self.done:
            return False
        self.done.add(bb.epoch)
        sid = self._source_id(bb, "injected fault: a confident hypothesis source that is wrong")
        posted = self._post(bb, self.faults.wrong_structures(), [sid], why="confident", fault="bad_llm")
        if posted:
            self.faults.hit("bad_llm")
        return posted
