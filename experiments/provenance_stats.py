"""Provenance of every crowned champion, read from saved blackboards (Blackboard.to_jsonl files).

For each champion artifact it walks the parent DAG and reports:
  agent types   distinct agent types among all its ancestors (explorer-0 and explorer-1 are one type)
  competing     the hypotheses the crowned model was fit with, grouped by source; "disagreed" means at
                least two sources proposed and their first structures differ
  won           which source proposed the structure the champion ended up with ("fit" when no
                hypothesis had it: the chain fit's own restarts or type search found it); a source
                injected as a fault is shown as source(fault)
When results/sweep.jsonl has the job, the champion's structure is also checked against the hidden body
(scoring only, never shown to an agent).

  python experiments/provenance_stats.py                       # results/blackboards (written by sweep.py)
  python experiments/provenance_stats.py some/dir a.jsonl ... --out results/provenance
"""
import argparse
import csv
import glob
import gzip
import json
import os
import re
from collections import Counter, defaultdict

import numpy as np


def read_board(path):
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as f:
        return {r["id"]: r for r in map(json.loads, f)}


def job_of(path):
    """(exp, params) from a sweep board name such as faults__family-arm__seed-1__fault-none__condition-swarm."""
    stem = re.sub(r"\.jsonl(\.gz)?$", "", os.path.basename(path))
    parts = stem.split("__")
    params = dict(p.split("-", 1) for p in parts[1:] if "-" in p)
    return parts[0], params


def agent_type(author):
    return re.sub(r"-\d+$", "", author)


def ancestors(nodes, start):
    seen, todo = set(), [start]
    while todo:
        i = todo.pop()
        for p in nodes.get(i, {}).get("parents", []):
            if p not in seen and p in nodes:
                seen.add(p)
                todo.append(p)
    return seen


def champion_rows(nodes):
    rows = []
    for c in (r for r in nodes.values() if r["kind"] == "champion"):
        anc = ancestors(nodes, c["id"])
        types = sorted({agent_type(nodes[i]["author"]) for i in anc | {c["id"]}})
        model = nodes[c["payload"]["candidate"]]
        tried = [nodes[i] for i in model["parents"] if nodes[i]["kind"] == "hypothesis"]
        by_src = defaultdict(list)
        for h in tried:
            src = h["payload"]["source"] + ("(fault)" if h["payload"].get("fault") else "")
            by_src[src].append(h["payload"])
        firsts = {s: tuple(min(hs, key=lambda h: h["rank"])["pattern"]) for s, hs in by_src.items()}
        found = (c["payload"].get("describe") or {}).get("structure")
        won = sorted(s for s, hs in by_src.items() if any(h["pattern"] == found for h in hs)) or ["fit"]
        rows.append({"champion": c["id"], "epoch": c["epoch"], "author": c["author"],
                     "n_agent_types": len(types), "agent_types": " ".join(types),
                     "sources": " ".join(sorted(by_src)), "n_sources": len(by_src),
                     "disagreed": len(firsts) >= 2 and len(set(firsts.values())) > 1,
                     "won": "+".join(won), "structure": " ".join(found or []),
                     "holdout_mm": c["payload"].get("holdout_mm")})
    if rows:
        rows[-1]["final"] = True
    return rows


def load_truth(path):
    truth = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "truth" in r.get("meta", {}):
                    truth[(r["exp"], tuple(sorted((k, str(v)) for k, v in r["params"].items())))] = r["meta"]["truth"]
    return truth


def group_name(exp, p):
    extra = p.get("fault") or p.get("damage") or (f"{p['noise_mm']} mm" if "noise_mm" in p else "")
    return exp, extra, p.get("condition", "?")


def summarize(rows, final_only):
    rs = [r for r in rows if r.get("final")] if final_only else rows
    if not rs:
        return None
    types = [r["n_agent_types"] for r in rs]
    multi = [r for r in rs if r["n_sources"] >= 2]
    won = Counter(w for r in rs for w in r["won"].split("+"))
    ok = [r["correct"] for r in rs if r.get("correct") is not None]
    return {"n": len(rs), "types": f"{np.median(types):.0f} ({min(types)} to {max(types)})",
            "multi": len(multi), "disagreed": sum(r["disagreed"] for r in multi),
            "won": ", ".join(f"{s} {k}" for s, k in won.most_common()),
            "correct": f"{sum(ok)}/{len(ok)}" if ok else "n/a"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", default=["results/blackboards"])
    ap.add_argument("--sweep", default="results/sweep.jsonl", help="job truths, for scoring only")
    ap.add_argument("--out", default="results/provenance")
    a = ap.parse_args()
    files = []
    for p in a.paths:
        files += sorted(glob.glob(os.path.join(p, "*.jsonl*"))) if os.path.isdir(p) else [p]
    if not files:
        raise SystemExit(f"no blackboards in {a.paths}; run experiments/sweep.py first (it saves them)")
    truth = load_truth(a.sweep)
    all_rows, groups = [], defaultdict(list)
    for path in files:
        exp, params = job_of(path)
        t = truth.get((exp, tuple(sorted(params.items()))))
        rows = champion_rows(read_board(path))
        for r in rows:
            r.update({"board": os.path.basename(path), "exp": exp, **params})
            r["correct"] = None if t is None else r["structure"].split() == list(t)
        all_rows += rows
        groups[group_name(exp, params)] += rows

    os.makedirs(a.out, exist_ok=True)
    keys = sorted({k for r in all_rows for k in r})
    with open(os.path.join(a.out, "champions.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(all_rows)

    lines = [f"# Provenance of crowned champions ({len(files)} boards, {len(all_rows)} champions)", "",
             "Agent types: distinct agent types among a champion's ancestors, median (range). Competing: champions "
             "whose model was fit with hypotheses from two or more sources, and how many of those had sources whose "
             "first structures disagreed. Won: whose proposal the champion's structure came from (fit = no "
             "hypothesis had it). Pipeline authors are stages of one orchestrator, not independent agents.", ""]
    for final_only, title in ((False, "Every champion"), (True, "Final champion of each run")):
        lines += [f"## {title}", "",
                  "| experiment | setting | condition | champions | agent types | competing (disagreed) | won | structure right |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for (exp, extra, cond), rows in sorted(groups.items()):
            s = summarize(rows, final_only)
            if s:
                lines.append(f"| {exp} | {extra} | {cond} | {s['n']} | {s['types']} | {s['multi']} ({s['disagreed']}) | "
                             f"{s['won']} | {s['correct']} |")
        lines.append("")
    open(os.path.join(a.out, "provenance.md"), "w").write("\n".join(lines))
    print("\n".join(lines))
    print(f"per champion rows: {os.path.join(a.out, 'champions.csv')}")
