"""Mirror a BodyScout Blackboard into ScienceClaw's artifact store, and expose the robot as a skill.

Our Blackboard stays the runtime. This module only copies it out, in the shapes
lamm-mit/scienceclaw reads (artifacts/artifact.py, artifacts/needs.py, artifacts/pressure.py):

  ~/.scienceclaw/artifacts/{producer_agent}/store.jsonl   full artifacts
  ~/.scienceclaw/artifacts/global_index.jsonl             metadata + needs, scanned by ArtifactReactor

(1) Every Blackboard artifact becomes a ScienceClaw Artifact. Each of our agents is its own
    producer_agent ("BodyScout.explorer0"), int ids become stable UUIDs, parents become
    parent_artifact_ids, so the DAG keeps every edge back to raw motions.
(2) Every Blackboard need becomes a carrier artifact whose `needs` list holds one NeedItem.
    Artifacts that served a need cite it as a parent and carry `_fulfilled_need`, which is how
    ScienceClaw's pressure scorer counts coverage. Our own pressure rides along on the NeedItem.
(3) `robot_motion` is BlackBoxRobot.move as a ScienceClaw skill: argparse, `--format json`, JSON
    on stdout. It only calls .move, .n_channels and .limits; it never returns ground truth.

No network: we write the JSONL files directly instead of calling ArtifactStore.save, which also
POSTs to Infinite and signs attestations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .blackboard import Artifact, Blackboard, Need

AGENT_PREFIX = "BodyScout"
SCHEMA_VERSION = "1.0"  # ScienceClaw Artifact.schema_version
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/lamm-mit/scienceclaw#bodyscout")
SKILL_SRC = Path(__file__).resolve().parent.parent / "scienceclaw_skill" / "robot_motion"

# Our artifact kinds -> ScienceClaw artifact_type (values from their SKILL_DOMAIN_MAP)
KIND_TO_TYPE = {
    "observation": "tabular_data",
    "finding": "analysis_result",
    "source": "report",
    "hypothesis": "synthesis",
    "model": "ml_prediction",
    "verdict": "peer_validation",
    "vote": "peer_validation",
    "disagreement": "peer_validation",
    "champion": "candidate_ranking",
    "score": "analysis_result",
    "anomaly": "analysis_result",
}
# Our need kinds -> the artifact_type a NeedItem asks for (must be in their ArtifactTypeLiteral)
NEED_TO_TYPE = {"data": "tabular_data", "probe": "tabular_data",
                "hypotheses": "synthesis", "relearn": "ml_prediction"}
NEED_CARRIER_TYPE = "raw_output"  # ScienceClaw's fallback type; the payload is our Need


def default_root() -> Path:
    return Path.home() / ".scienceclaw"


def scienceclaw_id(investigation_id: str, local_id: int) -> str:
    """Same run + same Blackboard id always gives the same UUID, so re-exports are idempotent."""
    return str(uuid.uuid5(_NS, f"{investigation_id}/{local_id}"))


def producer(author: str) -> str:
    return f"{AGENT_PREFIX}.{re.sub(r'[^A-Za-z0-9_.-]', '_', author)}"


def _clean(v: Any):
    """JSON safe copy; drops our private `_` keys (live models), same rule as Blackboard.to_jsonl."""
    if hasattr(v, "tolist"):
        return v.tolist()
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items() if not str(k).startswith("_")}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, float) and v != v:
        return None
    return v if isinstance(v, (int, float, str, bool, type(None))) else str(v)


def _hash_payload(payload: dict) -> str:
    """ScienceClaw's Artifact._hash_payload: sha256 of canonical JSON."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def map_need(n: Need) -> dict:
    """One of our needs as a ScienceClaw NeedItem dict, with our pressure kept alongside."""
    base = n.kind.split(":")[0]
    why = n.payload.get("why")
    if base == "probe":
        query = f"robot_motion probes of command channel {n.payload.get('channel', n.kind.split(':')[-1])}"
    else:
        query = f"robot_motion {n.kind} for BodyScout self model"
    rationale = f"{n.author} needs {n.kind}" + (f": {why}" if why else "") + \
        f" (BodyScout pressure {n.pressure:g}; explorers serve the highest pressure first)"
    return {
        "artifact_type": NEED_TO_TYPE.get(base, "analysis_result"),
        "query": query,
        "rationale": rationale,
        "branch": False,
        "max_variants": 1,
        "preferred_skills": ["robot_motion"] if NEED_TO_TYPE.get(base) == "tabular_data" else [],
        "param_variants": [],
        # extra keys: NeedItem ignores them, our importer and a judge reading the index do not
        "pressure": float(n.pressure),
        "bodyscout_need": n.kind,
        "open": bool(n.open),
    }


def _records(bb: Blackboard, investigation_id: str) -> list[dict]:
    """Every need and artifact on the board as a ScienceClaw Artifact dict (store.jsonl shape)."""
    sid = lambda i: scienceclaw_id(investigation_id, i)  # noqa: E731
    needs = {n.id: n for n in bb.needs}
    t0 = min([a.t for a in bb.artifacts], default=0.0)
    out = []
    for n in bb.needs:
        payload = {"_bodyscout": {"id": n.id, "kind": "need", "need": n.kind, "author": n.author,
                                  "pressure": float(n.pressure), "open": bool(n.open)},
                   **_clean(n.payload)}
        out.append(_record(sid(n.id), NEED_CARRIER_TYPE, n.author, "bodyscout_need", payload,
                           investigation_id, _iso(t0), [], [map_need(n)],
                           f"{n.author} opened need {n.kind} at pressure {n.pressure:g}"))
    for a in bb.artifacts:
        payload = {"_bodyscout": {"id": a.id, "kind": a.kind, "author": a.author, "epoch": a.epoch},
                   **_clean(a.payload)}
        served = [p for p in a.parents if p in needs]
        if served:  # lets ScienceClaw's pressure.py count this need as covered
            n = needs[served[0]]
            payload["_fulfilled_need"] = {"parent_artifact_id": sid(n.id),
                                          "artifact_type": map_need(n)["artifact_type"],
                                          "query": map_need(n)["query"]}
            payload["_need_index"] = 0
        skill = "robot_motion" if a.kind == "observation" else f"bodyscout_{a.kind}"
        out.append(_record(sid(a.id), KIND_TO_TYPE.get(a.kind, "analysis_result"), a.author, skill,
                           payload, investigation_id, _iso(a.t), [sid(p) for p in a.parents], [],
                           f"{a.author} posted {a.kind} #{a.id} (epoch {a.epoch})"))
    return out


def _record(aid, atype, author, skill, payload, inv, ts, parents, needs, summary) -> dict:
    return {"artifact_id": aid, "artifact_type": atype, "producer_agent": producer(author),
            "skill_used": skill, "schema_version": SCHEMA_VERSION, "payload": payload,
            "investigation_id": inv, "timestamp": ts, "content_hash": _hash_payload(payload),
            "parent_artifact_ids": parents, "result_quality": "ok", "needs": needs, "summary": summary}


def _index_entry(r: dict) -> dict:
    """ScienceClaw's ArtifactStore._append_global_index entry for one artifact."""
    fn = r["payload"].get("_fulfilled_need") or {}
    return {"artifact_id": r["artifact_id"], "artifact_type": r["artifact_type"],
            "producer_agent": r["producer_agent"], "skill_used": r["skill_used"],
            "investigation_id": r["investigation_id"], "timestamp": r["timestamp"],
            "content_hash": r["content_hash"], "parent_artifact_ids": r["parent_artifact_ids"],
            "needs": r["needs"],
            "fulfilled_need_parent_id": fn.get("parent_artifact_id", ""),
            "fulfilled_need_index": r["payload"].get("_need_index"),
            "fulfilled_need_type": fn.get("artifact_type", ""),
            "fulfilled_need_query": fn.get("query", "")[:180],
            "fulfillment_variant": {}}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def export_blackboard(bb: Blackboard, investigation_id: str, root: Path | str | None = None) -> dict:
    """Append the board to ScienceClaw's stores. Artifacts already exported are skipped.

    Needs are re-mirrored only when new, so a need's `open` flag reflects the first export;
    call this once at the end of a run for a faithful snapshot.
    """
    base = Path(root or default_root()) / "artifacts"
    base.mkdir(parents=True, exist_ok=True)
    index = base / "global_index.jsonl"
    seen = {e.get("artifact_id") for e in _read_jsonl(index)}
    new = [r for r in _records(bb, investigation_id) if r["artifact_id"] not in seen]
    by_agent: dict[str, list[dict]] = {}
    for r in new:
        by_agent.setdefault(r["producer_agent"], []).append(r)
    for agent, rows in by_agent.items():
        (base / agent).mkdir(parents=True, exist_ok=True)
        with open(base / agent / "store.jsonl", "a", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    with open(index, "a", encoding="utf-8") as f:
        f.writelines(json.dumps(_index_entry(r), ensure_ascii=False) + "\n" for r in new)
    return {"written": len(new), "skipped": len(bb.artifacts) + len(bb.needs) - len(new),
            "agents": sorted(by_agent), "index": str(index)}


def import_blackboard(investigation_id: str, root: Path | str | None = None) -> Blackboard:
    """Rebuild a Blackboard from ScienceClaw's stores. Parents come from parent_artifact_ids,
    so this checks the lineage survived, not just our private copy of it."""
    base = Path(root or default_root()) / "artifacts"
    agents = sorted({e["producer_agent"] for e in _read_jsonl(base / "global_index.jsonl")
                     if e.get("investigation_id") == investigation_id
                     and e.get("producer_agent", "").startswith(AGENT_PREFIX + ".")})
    full = {r["artifact_id"]: r for a in agents for r in _read_jsonl(base / a / "store.jsonl")
            if r.get("investigation_id") == investigation_id}
    local = {aid: r["payload"]["_bodyscout"]["id"] for aid, r in full.items()}
    bb = Blackboard()
    arts, needs = [], []
    for r in full.values():
        meta = r["payload"]["_bodyscout"]
        payload = {k: v for k, v in r["payload"].items() if not k.startswith("_")}
        if meta["kind"] == "need":
            needs.append(Need(meta["id"], meta["need"], meta["author"], meta["pressure"], payload, meta["open"]))
        else:
            t = datetime.fromisoformat(r["timestamp"]).timestamp()
            arts.append(Artifact(meta["id"], meta["kind"], meta["author"], meta["epoch"], payload,
                                 [local[p] for p in r["parent_artifact_ids"]], t))
    bb.artifacts = sorted(arts, key=lambda a: a.id)
    bb.needs = sorted(needs, key=lambda n: n.id)
    bb.epoch = max([a.epoch for a in arts], default=0)
    return bb


# ---- (3) the robot as a ScienceClaw skill -------------------------------------------------

def robot_motion(robot, commands=None, n: int = 8, seed: int = 0) -> dict:
    """Run motions through BlackBoxRobot.move. Uses only .move, .n_channels and .limits."""
    import numpy as np
    lo, hi = robot.limits
    if commands is None:
        commands = np.random.default_rng(seed).uniform(lo, hi, (n, robot.n_channels))
    results = []
    for q in commands:
        q = np.asarray(q, float)
        if q.shape != (robot.n_channels,):
            raise ValueError(f"each command needs {robot.n_channels} channels, got {q.shape}")
        results.append({"q": q.round(6).tolist(), "x_mm": (robot.move(q) * 1000).round(3).tolist()})
    return {"n_channels": robot.n_channels, "limits": [lo, hi], "motions": len(results),
            "results": results,
            "summary": f"{len(results)} motions on a {robot.n_channels} channel body, tip in mm"}


def _parse_body(text: str) -> tuple[str, int] | None:
    from .world import FAMILIES
    m = re.search(rf"\b({'|'.join(FAMILIES)})[ _-]?(\d+)\b", text or "")
    return (m.group(1), int(m.group(2))) if m else None


def robot_motion_cli(argv=None) -> int:
    """ScienceClaw skill entry point (skills/robot_motion/scripts/robot_motion.py calls this)."""
    from .world import FAMILIES, BlackBoxRobot, random_body
    ap = argparse.ArgumentParser(description="Command a black box jointed robot and observe its tip")
    ap.add_argument("--query", default="", help="free text; a body handle like 'arm3' or 'scara7' picks the robot")
    ap.add_argument("--family", choices=FAMILIES, default=None)
    ap.add_argument("--seed", type=int, default=None, help="which body of the family")
    ap.add_argument("--commands", default=None, help="JSON list of channel command vectors (radians or slide units)")
    ap.add_argument("--n", type=int, default=8, help="random motions when --commands is absent")
    ap.add_argument("--motion-seed", type=int, default=0)
    ap.add_argument("--damage", default=None, help="apply this damage kind before moving")
    ap.add_argument("--format", default="json", choices=["summary", "json"])
    a = ap.parse_args(argv)
    fam, seed = _parse_body(a.query) or ("arm", 3)
    fam, seed = a.family or fam, a.seed if a.seed is not None else seed
    robot = BlackBoxRobot(random_body(seed, fam), seed=seed)
    if a.damage:
        robot.damage(a.damage, seed=seed)  # the world changes; the skill reports no details of how
    out = {"query": a.query or f"{fam}{seed}", "body": f"{fam}{seed}", "damaged": bool(a.damage),
           **robot_motion(robot, json.loads(a.commands) if a.commands else None, a.n, a.motion_seed)}
    if a.format == "json":
        print(json.dumps(out))
    else:
        print(out["summary"])
        for r in out["results"]:
            print(f"  q={r['q']}  ->  x_mm={r['x_mm']}")
    return 0


def install_skill(scienceclaw_dir: Path | str) -> Path:
    """Copy the robot_motion skill into a ScienceClaw checkout so its registry discovers it."""
    dest = Path(scienceclaw_dir) / "skills" / "robot_motion"
    shutil.copytree(SKILL_SRC, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    (dest / "bodyscout_root.txt").write_text(str(SKILL_SRC.parent.parent), encoding="utf-8")
    return dest


if __name__ == "__main__":
    sys.exit(robot_motion_cli())
