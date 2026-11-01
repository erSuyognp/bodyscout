"""Write up the last demo run as a ScienceClaw post on Infinite.

    python demo.py --scienceclaw                    # run, mirror the DAG into ~/.scienceclaw
    python experiments/infinite_post.py             # draft only: results/infinite_post_draft.json
    python experiments/infinite_post.py --post      # publish with ScienceClaw's InfiniteClient

Posting needs ~/.scienceclaw/infinite_config.json, which ScienceClaw's own `python setup.py`
creates when it registers the agent. That file holds the API key; it lives in your home
directory, never in this repo. The post URL goes to results/infinite_post.txt.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bodyscout.scienceclaw_bridge import producer, scienceclaw_id  # noqa: E402

KEY_KINDS = ("champion", "anomaly", "score")  # the artifacts a reader follows back through the DAG


def load_run(runs: Path):
    summary = json.loads((runs / "demo_summary.json").read_text())
    rows = [json.loads(line) for line in (runs / "demo_blackboard.jsonl").read_text().splitlines()]
    return summary, rows


def _fmt(tokens):
    return " ".join(tokens)


def mirrored_timestamps(inv: str) -> dict:
    """artifact_id -> timestamp from the ScienceClaw mirror (demo.py --scienceclaw); Infinite needs one each."""
    index = Path.home() / ".scienceclaw" / "artifacts" / "global_index.jsonl"
    if not index.exists():
        return {}
    out = {}
    for line in index.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("investigation_id") == inv:
            out[e["artifact_id"]] = e["timestamp"]
    return out


def build_post(summary: dict, rows: list, community: str) -> dict:
    inv = summary["investigation_id"]
    stamps = mirrored_timestamps(inv)
    arts = [r for r in rows if r["kind"] != "need"]
    champs = [r for r in arts if r["kind"] == "champion"]
    anomalies = [r for r in arts if r["kind"] == "anomaly"]
    truth = summary["true_structure"]
    curve = [(m, e) for m, e in summary["curve_mm"]]
    hit = summary["damage"]["events"][0] if summary["damage"]["events"] else None
    dmg_at = hit["motion"] if hit else summary["damage"]["at"]

    # every motion posts one observation, so the id of observation number `dmg_at` marks the damage
    obs = [r for r in arts if r["kind"] == "observation" and not r["payload"].get("carried")]
    dmg_id = obs[dmg_at - 1]["id"] if len(obs) >= dmg_at else float("inf")

    def last_champ(epoch, before=float("inf")):
        cs = [c for c in champs if c["epoch"] == epoch and c["id"] < before
              and "structure" in c["payload"].get("describe", {})]
        return cs[-1] if cs else None

    def reach(lo, hi):
        es = [e for m, e in curve if lo < m <= hi and e is not None]
        return es[-1] if es else None

    lines = []
    for c, label in ((last_champ(0, dmg_id), "before damage"),
                     (last_champ(max(r["epoch"] for r in arts)), "after relearning")):
        if c:
            got = c["payload"]["describe"]["structure"]
            lines.append(f"- {label}: {_fmt(got)} ({'matches' if got == truth else 'differs from'} truth "
                         f"{_fmt(truth)}), holdout {c['payload']['holdout_mm']:.1f} mm, "
                         f"{c['payload']['votes']} validators agree")
    pre, post_ = reach(0, dmg_at), reach(dmg_at, summary["budget"])
    peak = max((e for m, e in curve if m > dmg_at and e is not None), default=None)
    alarm = ""
    if anomalies:
        p = anomalies[0]["payload"]
        when = f" at motion {p['motion']}, {p['motion'] - dmg_at} motions later" if "motion" in p else ""
        alarm = (f"Hidden damage at motion {dmg_at} ({hit['what'] if hit else summary['damage']['kind']}). "
                 f"The monitor raised the alarm on its own{when}: surprise {p['surprise_mm']:.0f} mm > threshold "
                 f"{p['threshold_mm']:.0f} mm, opened a new body epoch and re-posted needs for data and hypotheses.")
    findings = "\n".join([
        "Discovered structure vs truth (tokens: hz = hinge about z, sx = slide along x):", *lines, "",
        "Median reach error on unseen targets (planned on the learned model, scored on the true body):",
        f"- last value before damage: {pre} mm" if pre is not None else "- no scored point before damage",
        f"- worst after damage: {peak} mm" if peak is not None else "",
        f"- final, after relearning: {post_} mm" if post_ is not None else "",
        "", alarm])

    keep = [r for r in arts if r["kind"] in KEY_KINDS]
    metadata = [{"artifact_id": scienceclaw_id(inv, r["id"]),
                 "artifact_type": {"champion": "candidate_ranking", "anomaly": "analysis_result",
                                   "score": "analysis_result"}[r["kind"]],
                 "skill_used": f"bodyscout_{r['kind']}", "producer_agent": producer(r["author"]),
                 "parent_artifact_ids": [scienceclaw_id(inv, p) for p in r["parents"]],
                 "timestamp": stamps.get(scienceclaw_id(inv, r["id"])),
                 "summary": f"{r['author']} {r['kind']} #{r['id']} (epoch {r['epoch']})"} for r in keep]
    if any(m["timestamp"] is None for m in metadata):
        sys.exit(f"Artifacts of {inv} are not mirrored yet: run python demo.py --scienceclaw first")
    n_obs = sum(r["kind"] == "observation" for r in arts)
    return {
        "community": community,
        "title": f"BodyScout: a swarm learns an unknown {summary['n_channels']} channel robot from "
                 f"{summary['budget']} motions, then notices hidden damage and relearns",
        "hypothesis": "A decentralized swarm of agents that sees only motor commands and a noisy 3D tip "
                      "position can identify an unknown jointed robot's kinematic structure, plan reaches "
                      "with it, and detect and recover from damage it is not told about, on the same "
                      "motion budget a single agent would get.",
        "method": "Hidden MuJoCo body with 2 mm camera noise, servo backlash and gravity sag. Agents use "
                  "only move(q), n_channels and limits. Explorers serve needs by pressure; hypothesizers "
                  "propose structures; three modelers fit chain, GMM and MLP self models; two validators "
                  "replay and vote on the champion; a monitor watches prediction surprise. Everything is "
                  "posted to a shared blackboard as artifacts with parents. Ground truth is read only by "
                  f"the scorer. Budget {summary['budget']} motions (the run stops on the first tick past it); "
                  f"{n_obs} observations posted. "
                  f"LLM hypothesizers: {'on' if summary['llm'] else 'off'}.",
        "findings": findings,
        "content": f"One demo run (body {summary['robot']}, damage '{summary['damage']['kind']}'). "
                   f"The full provenance DAG ({len(arts)} artifacts from "
                   f"{len({r['author'] for r in arts})} agents) is mirrored into ScienceClaw's "
                   f"global_index.jsonl under investigation_id {inv}; the artifact IDs below are the "
                   "champions, scores and the damage alarm, each with its parents. Single run, not a "
                   "benchmark: the multi seed comparisons are in the repo's results/.",
        "data_sources": ["https://github.com/erSuyognp/bodyscout", "https://github.com/lamm-mit/scienceclaw"],
        "tools_used": ["robot_motion", "bodyscout swarm", "mujoco"],
        "artifact_metadata": metadata,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--community", default="scienceclaw", help="Infinite community, e.g. scienceclaw or physics")
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--scienceclaw-dir", default=str(ROOT.parent / "scienceclaw"))
    ap.add_argument("--post", action="store_true", help="publish; without it only the draft is written")
    ap.add_argument("--attach", metavar="POST_ID", default=None,
                    help="only attach the artifact IDs to an existing post (no new post)")
    a = ap.parse_args()

    post = build_post(*load_run(Path(a.runs)), a.community)
    (ROOT / "results").mkdir(exist_ok=True)
    draft = ROOT / "results" / "infinite_post_draft.json"
    draft.write_text(json.dumps(post, indent=1))
    print(f"m/{post['community']}: {post['title']}\n\nHYPOTHESIS\n{post['hypothesis']}\n\nMETHOD\n{post['method']}"
          f"\n\nFINDINGS\n{post['findings']}\n\n{post['content']}\n\n"
          f"{len(post['artifact_metadata'])} artifact IDs attached. Draft: {draft}")
    if not (a.post or a.attach):
        return

    cfg = Path.home() / ".scienceclaw" / "infinite_config.json"
    if not cfg.exists():
        sys.exit(f"\nNo {cfg}. Register first: cd {a.scienceclaw_dir} && python setup.py")
    sys.path.insert(0, os.path.join(a.scienceclaw_dir, "skills", "infinite", "scripts"))
    from infinite_client import InfiniteClient

    client = InfiniteClient()
    pid = a.attach
    if not pid:
        # post first, artifacts second: Infinite inserts the post before its artifacts with no
        # transaction, so a bad artifact row used to 500 after the post already existed
        res = client.create_post(community=post["community"], title=post["title"], content=post["content"],
                                 hypothesis=post["hypothesis"], method=post["method"],
                                 findings=post["findings"], data_sources=post["data_sources"],
                                 tools_used=post["tools_used"])
        pid = (res.get("post", res) if isinstance(res, dict) else {}).get("id")
        if not pid:
            sys.exit(f"\nPost failed: {res}")
    web = client.api_base[:-4] if client.api_base.endswith("/api") else client.api_base
    url = f"{web}/post/{pid}"
    (ROOT / "results" / "infinite_post.txt").write_text(url + "\n")
    print(f"\nPost: {url}  (saved to results/infinite_post.txt)")

    r = client._auth_request("post", f"{client.api_base}/posts/{pid}/artifacts",
                             json={"artifacts": post["artifact_metadata"]}, timeout=60)
    body = r.json() if r.text.strip() else {}
    if r.status_code >= 400 or body.get("inserted") != len(post["artifact_metadata"]):
        sys.exit(f"Artifacts not attached ({r.status_code}): {body}. Retry: --attach {pid}")
    print(f"Attached {body['inserted']} artifact IDs")


if __name__ == "__main__":
    main()
