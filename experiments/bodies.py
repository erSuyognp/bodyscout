"""Experiment 4: one system for any jointed body. Arms, gantries, SCARA and telescoping robots,
and nobody tells the agents which is which. Swarm (with channel agents) vs single agent (blind
structure search), same budget. Structure accuracy is scored here, never inside an agent."""
import os

# Pin BLAS/OpenMP to one thread before numpy or scipy load: threaded reductions sum in a
# varying order, which makes least squares fits differ run to run.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import json
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import save_csv  # noqa: E402

from bodyscout.swarm import run  # noqa: E402
from bodyscout.world import FAMILIES, BlackBoxRobot, random_body  # noqa: E402

def job(args):
    fam, seed, cond, budget = args
    robot = BlackBoxRobot(random_body(seed, fam), seed=seed)
    out = run(robot, cond, budget=budget, eval_at=(16, 24, 32, 48, 64), n_targets=8, seed=seed,
              use_llm=False, unknown_body=True)
    d = (out["champion"] or {}).get("describe") or {}
    truth = robot.spec.tokens()
    found = d.get("structure")
    rows = [{"family": fam, "seed": seed, "condition": cond, "motions": m, "reach_mm": e} for m, e in out["curve"]]
    meta = {"family": fam, "seed": seed, "condition": cond, "truth": truth, "found": found,
            "types_correct": found is not None and [t[0] for t in found] == [t[0] for t in truth],
            "structure_correct": found == truth, "links_m": d.get("links_m"),
            "identifiable": d.get("identifiable")}
    return rows, meta


if __name__ == "__main__":  # Windows spawns workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--budget", type=int, default=64)
    ap.add_argument("--families", nargs="+", default=list(FAMILIES))
    a = ap.parse_args()
    jobs = [(f, s, c, a.budget) for f in a.families for s in range(1, a.seeds + 1) for c in ("swarm", "single")]
    with Pool(os.cpu_count()) as p:
        res = p.map(job, jobs)
    save_csv([r for rs, _ in res for r in rs], "results/bodies.csv")
    json.dump([m for _, m in res], open("results/bodies_meta.json", "w"), indent=1)
    for c in ("swarm", "single"):
        ms = [m for _, m in res if m["condition"] == c]
        print(f"{c:7s} joint types right {sum(m['types_correct'] for m in ms)}/{len(ms)}, "
              f"full structure right {sum(m['structure_correct'] for m in ms)}/{len(ms)}")
