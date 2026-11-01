"""Experiment 2: break the robot mid run. Who notices, and how fast do they recover? Body type unknown
(channel agents on), so single_probe can be compared on the same footing."""
import argparse
import json

from common import run_jobs, save_csv

if __name__ == "__main__":  # Windows spawns workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", type=int, default=3)
    ap.add_argument("--kinds", nargs="+", default=["long_link", "reversed_motor", "tool", "bent_axis"])
    ap.add_argument("--at", type=int, default=48)
    ap.add_argument("--budget", type=int, default=112)
    ap.add_argument("--conditions", nargs="+", default=["swarm", "single", "single_probe"])
    a = ap.parse_args()

    rows, metas = [], []
    jobs = []
    for kind in a.kinds:
        kw = {"budget": a.budget, "eval_at": tuple(range(8, a.budget + 1, 4)), "n_targets": 8,
              "damage": (a.at, kind), "max_ticks": 600, "use_llm": False, "unknown_body": True}
        jobs += [(s, c, kw) for s in range(1, a.arms + 1) for c in a.conditions]
    for (s, c, kw), (rs, meta) in zip(jobs, run_jobs(jobs)):
        for r in rs:
            r["damage"] = kw["damage"][1]
        meta["damage"] = kw["damage"][1]
        rows += rs
        metas.append(meta)
    save_csv(rows, "results/damage.csv")
    json.dump(metas, open("results/damage_meta.json", "w"), indent=1, default=str)
    print("saved results/damage.csv", len(rows), "rows")
