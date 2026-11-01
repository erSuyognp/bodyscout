import numpy as np

from bodyscout.blackboard import Blackboard
from bodyscout.models import ChainModel
from bodyscout.world import BlackBoxRobot, random_arm


def test_robot_moves_and_counts():
    r = BlackBoxRobot(random_arm(1), seed=1)
    x = r.move(np.zeros(r.n_channels))
    assert x.shape == (3,) and r.motions == 1


def test_chain_recovers_structure():
    spec = random_arm(1)
    r = BlackBoxRobot(spec, seed=1)
    rng = np.random.default_rng(0)
    Q = rng.uniform(-2, 2, (60, r.n_channels))
    X = np.array([r.move(q) for q in Q])
    m = ChainModel(r.n_channels, restarts=3).fit(Q, X)
    Qh = rng.uniform(-2, 2, (30, r.n_channels))
    Xh = np.array([r.true_tip(q) for q in Qh])
    assert m.rmse(Qh, Xh) < 0.008  # under 8 mm with 2 mm camera noise


def test_damage_changes_body():
    r = BlackBoxRobot(random_arm(2), seed=2)
    q = np.full(r.n_channels, 0.4)
    before = r.true_tip(q)
    r.damage("tool")
    assert np.linalg.norm(r.true_tip(q) - before) > 0.02


def test_blackboard_needs_merge_and_claim():
    bb = Blackboard()
    bb.need("data", "a", 1.0)
    bb.need("data", "b", 5.0)
    n = bb.claim("data")
    assert n.pressure == 5.0 and bb.claim("data") is None


def test_chain_fits_slide_joints_when_structure_known():
    from bodyscout.world import random_body
    spec = random_body(1, "gantry")
    r = BlackBoxRobot(spec, seed=1)
    rng = np.random.default_rng(0)
    Q = rng.uniform(-2, 2, (40, r.n_channels))
    X = np.array([r.move(q) for q in Q])
    m = ChainModel(r.n_channels, restarts=1).fit(Q, X, patterns=[spec.tokens()])
    assert m.tokens() == spec.tokens()


def _fit_known_structure(spec, n_motions=40):
    r = BlackBoxRobot(spec, seed=1)
    rng = np.random.default_rng(0)
    Q = rng.uniform(-2, 2, (n_motions, r.n_channels))
    X = np.array([r.move(q) for q in Q])
    return ChainModel(r.n_channels, restarts=1).fit(Q, X, patterns=[spec.tokens()]).describe()


def test_identifiability_flags_scara_height_but_not_arm_links():
    from bodyscout.world import random_body
    scara = _fit_known_structure(random_body(1, "scara"))  # links: horizontal, horizontal, vertical, tip
    assert scara["identifiable"][2] is False, scara        # height of the vertical link is invisible
    arm = random_arm(2)                                    # hz hy hy hy hy
    d = _fit_known_structure(arm)
    # link 0 (yaw to shoulder) trades off against the unknown base height; every later link is pinned
    assert d["identifiable"] == [False] + [True] * (arm.n - 1), d
    assert np.allclose(d["links_m"][1:], arm.links[1:], atol=0.005), (d["links_m"], arm.links)


def test_channel_agent_tells_slide_from_hinge():
    from bodyscout.agents import ChannelAgent, Explorer
    from bodyscout.world import random_body
    r = BlackBoxRobot(random_body(1, "scara"), seed=1)
    bb = Blackboard()
    ex = Explorer(r)
    agents = [ChannelAgent(i, r.n_channels) for i in range(r.n_channels)]
    for t in range(6):
        for ag in agents:
            ag.step(bb, t)
        ex.step(bb, t)
    types = {f.payload["channel"]: f.payload["type"] for f in bb.of("finding")}
    assert [types[i] for i in range(r.n_channels)] == r.spec.types


# ---- regression guards for CLAUDE.md rules ---------------------------------
import ast
import copy
import functools
import json
import pathlib
import re

import pytest

ALLOWED_ROBOT_ATTRS = {"move", "n_channels", "limits"}


def test_agents_only_touch_allowed_robot_attributes():
    src = pathlib.Path(__file__).resolve().parents[1] / "bodyscout" / "agents.py"
    used = set()
    for node in ast.walk(ast.parse(src.read_text())):
        if isinstance(node, ast.Attribute):
            v = node.value
            owner = v.id if isinstance(v, ast.Name) else v.attr if isinstance(v, ast.Attribute) else ""
            if owner.endswith("robot"):
                used.add(node.attr)
    assert used <= ALLOWED_ROBOT_ATTRS, f"agents touch hidden robot attributes: {used - ALLOWED_ROBOT_ATTRS}"


@functools.lru_cache(maxsize=None)
def _scara_run(budget, knockout=None):
    """Unknown body swarm run on a SCARA, snapshotting every champion payload the moment it is posted.
    Cached: several tests read the same run."""
    from bodyscout.swarm import run
    from bodyscout.world import random_body

    snaps = []
    orig = Blackboard.post

    def post(self, kind, author, payload, parents=None):
        art = orig(self, kind, author, payload, parents)
        if kind == "champion":
            snaps.append((art, copy.deepcopy({k: v for k, v in payload.items() if k != "_model"})))
        return art

    Blackboard.post = post
    try:
        robot = BlackBoxRobot(random_body(1, "scara"), seed=1)
        out = run(robot, "swarm", budget=budget, eval_at=(budget,), n_targets=4, seed=1, use_llm=False,
                  unknown_body=True, knockout=knockout and (knockout[0], list(knockout[1])))
    finally:
        Blackboard.post = orig
    out["truth"] = robot.spec.tokens()  # scoring only, read here in the test, never by an agent
    return out, snaps


def test_every_artifact_has_parents(tmp_path):
    out, _ = _scara_run(24)
    bb = out["blackboard"]
    path = tmp_path / "bb.jsonl"
    bb.to_jsonl(str(path))
    ids = {json.loads(line)["id"] for line in path.read_text().splitlines()}
    for a in bb.artifacts:
        if a.kind == "source":
            continue
        assert a.parents, f"{a.kind} #{a.id} by {a.author} has no parents"
        missing = set(a.parents) - ids
        assert not missing, f"{a.kind} #{a.id} cites ids missing from the JSONL: {missing}"


def test_artifacts_are_immutable():
    _, snaps = _scara_run(48)  # long enough to crown a champion and then grow the holdout set
    assert snaps, "the run crowned no champion, so nothing was checked"
    for art, before in snaps:
        now = {k: v for k, v in art.payload.items() if k != "_model"}
        assert now == before, f"champion #{art.id} was edited after posting"


# ---- no single point of failure --------------------------------------------
def test_crown_is_a_pure_public_rule():
    from bodyscout.agents import crown
    bb = _scara_run(48)[0]["blackboard"]
    n = len(bb.artifacts)
    first, second = crown(bb), crown(bb)
    assert first == second and len(bb.artifacts) == n, "crown(bb) must not change the board"
    assert first["champion"] is not None
    replays = [v.payload["replayed"] for v in bb.of("verdict") if v.payload["candidate"] == first["champion"]]
    assert True in replays and False not in replays, "crowned a candidate that did not pass replay"


def test_champions_carry_both_validators_votes():
    bb = _scara_run(48)[0]["blackboard"]
    assert not bb.of("disagreement", epoch=-1)
    byid = {a.id: a for a in bb.artifacts}
    champs = bb.of("champion", epoch=-1)
    assert champs
    for c in champs:
        votes = [byid[i] for i in c.parents if byid[i].kind == "vote"]
        assert {v.author for v in votes} == {"validator-0", "validator-1"}, c
        assert {v.payload["champion"] for v in votes} == {c.payload["candidate"]}


def test_structure_survives_losing_every_hypothesizer_a_validator_and_an_explorer():
    gone = ("hyp-channels", "hyp-prior", "hyp-library", "validator-0", "explorer-0")
    out, _ = _scara_run(48, knockout=(0, gone))
    bb = out["blackboard"]
    assert not bb.of("hypothesis", epoch=-1)            # nobody proposed anything
    assert out["champion"]["describe"]["structure"] == out["truth"]  # the chain modeler assembled findings
    assert all(c.payload["votes"] == 1 for c in bb.of("champion", epoch=-1))
    assert {a.author for a in bb.of("observation", epoch=-1)} <= {"explorer-1", "monitor"}


# ---- LLM hypothesizer (offline: the API call is faked) ---------------------
def _fake_claude_run(monkeypatch, family, ask):
    from bodyscout.agents import LLMHypothesizer
    from bodyscout.swarm import run
    from bodyscout.world import random_body

    calls = []  # (motions spent when called, prompt)
    robot = BlackBoxRobot(random_body(1, family), seed=1)
    monkeypatch.setattr(LLMHypothesizer, "_ask", lambda self, p: calls.append((robot.motions, p)) or ask(p))
    monkeypatch.setattr("bodyscout.swarm.llm_providers", lambda: ["claude"])
    out = run(robot, "swarm", budget=32, eval_at=(32,), n_targets=4, seed=1, use_llm=True,
              unknown_body=family != "arm")
    return out, calls


def test_claude_called_once_findings_are_in_and_why_is_posted(monkeypatch):
    def answer(prompt):
        n = int(re.search(r"has (\d+) unlabeled", prompt).group(1))
        return json.dumps({"patterns": [["hz"] * n], "why": "channel 2 moves the tip in a line"})
    out, calls = _fake_claude_run(monkeypatch, "scara", answer)
    bb = out["blackboard"]
    n = len({a.payload["channel"] for a in bb.of("finding")})
    assert len(calls) == 1, "one call per epoch, the answer is cached"
    assert calls[0][1].count("channel ") >= n and "spread_mm=" in calls[0][1], "findings go in the prompt"
    first = min(a.id for a in bb.of("hypothesis") if a.payload["source"] == "claude")
    assert max(a.id for a in bb.of("finding")) < first, "called only after every channel reported"
    hs = [a for a in bb.of("hypothesis") if a.payload["source"] == "claude"]
    assert hs and hs[0].payload["why"] == "channel 2 moves the tip in a line"
    assert {a.id for a in bb.of("finding")} <= set(hs[0].parents), "provenance cites the findings"


def test_claude_called_at_8_motions_on_a_known_arm_and_failures_are_quiet(monkeypatch):
    def boom(prompt):
        raise TimeoutError
    out, calls = _fake_claude_run(monkeypatch, "arm", boom)
    n_rows = calls[0][1].count("q=") if calls else 0
    # agents step in a random order each tick, so up to two explorer batches can land before its turn
    assert len(calls) == 1 and 8 <= n_rows < 16, "called at the first chance after 8 train motions"
    assert not [a for a in out["blackboard"].of("hypothesis") if a.payload["source"] == "claude"]
    assert out["champion"] is not None, "the swarm carried on without Claude"
