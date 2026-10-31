"""Experiment 1: how fast does each condition learn an unknown body?
Same robots, same motion budget, scored by true reach error on unseen targets."""
import argparse
import json

from common import run_jobs, save_csv

if __name__ == "__main__":  # Windows spawns workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", type=int, default=5)
    ap.add_argument("--budget", type=int, default=64)
    ap.add_argument("--conditions", nargs="+", default=["swarm", "single", "mlp"])
    ap.add_argument("--llm", action="store_true", help="let the hypothesizer call Claude")
    a = ap.parse_args()

    checkpoints = (8, 12, 16, 24, 32, 48, 64, 96, 128)
    kw = {"budget": a.budget, "eval_at": tuple(c for c in checkpoints if c <= a.budget),
          "n_targets": 8, "use_llm": a.llm}
    jobs = [(s, c, kw) for s in range(1, a.arms + 1) for c in a.conditions]
    res = run_jobs(jobs)
    rows = [r for rs, _ in res for r in rs]
    save_csv(rows, "results/learning.csv")
    json.dump([m for _, m in res], open("results/learning_meta.json", "w"), indent=1, default=str)
    print("saved results/learning.csv", len(rows), "rows")
