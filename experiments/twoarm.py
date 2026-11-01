"""Two arms on one shared base. Per-limb structure accuracy and reach error.

Swarm, single_probe and single, body type unknown, same robots, same motion budget, same scorer.
A limb is correct when the crowned model names that fingertip's chain (shared trunk, then the limb)
in order. Reach error is the median true miss of that fingertip after executing the model's plan.
Both are scored here. Agents never see the spec.
"""
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
from bodyscout.world import BlackBoxRobot, random_body  # noqa: E402


def job(args):
    seed, cond, budget = args
    robot = BlackBoxRobot(random_body(seed, "twoarm"), seed=seed)
    out = run(robot, cond, budget=budget, eval_at=tuple(range(8, budget + 1, 8)), n_targets=8, seed=seed,
              use_llm=False, unknown_body=True)
    d = (out["champion"] or {}).get("describe") or {}
    truth = robot.spec.limb_tokens()  # scoring only
    found = d.get("limb_structure")
    flags = [bool(found) and i < len(found) and found[i] == limb for i, limb in enumerate(truth)]
    rows = []
    for motion, per in out.get("limb_curve") or []:
        for limb, err in enumerate(per):
            rows.append({"family": "twoarm", "seed": seed, "condition": cond, "limb": limb,
                         "motions": motion, "reach_mm": None if err != err else round(float(err), 2)})
    final_m = max((r["motions"] for r in rows), default=None)
    final = [next(r["reach_mm"] for r in rows if r["motions"] == final_m and r["limb"] == i)
             for i in range(len(truth))] if final_m is not None else [None] * len(truth)
    meta = {"family": "twoarm", "seed": seed, "condition": cond, "truth": truth, "found": found,
            "limbs": d.get("limbs"), "true_limbs": robot.spec.limbs, "structure_correct": flags,
            "final_reach_mm": final, "structure": d.get("structure")}
    return rows, meta


def _median(values):
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return float("nan")
    mid = len(xs) // 2
    if len(xs) % 2:
        return xs[mid]
    return 0.5 * (xs[mid - 1] + xs[mid])


def _report(metas, conditions):
    print("\nper limb: structure (chains right) and reach error at the last checkpoint")
    for cond in conditions:
        ms = [m for m in metas if m["condition"] == cond]
        if not ms:
            continue
        n_limbs = len(ms[0]["truth"])
        for limb in range(n_limbs):
            ok = sum(bool(m["structure_correct"][limb]) for m in ms)
            mid = _median(m["final_reach_mm"][limb] for m in ms)
            print(f"{cond:12} limb {limb}  structure {ok}/{len(ms)}  median reach {mid:7.1f} mm")
        for m in ms:
            got = m["found"] if m["found"] else ["-"] * len(m["truth"])
            print(f"  seed {m['seed']}  truth {m['truth']}")
            print(f"           found {got}  reach {m['final_reach_mm']}")


if __name__ == "__main__":  # Windows spawns workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--budget", type=int, default=64)
    ap.add_argument("--conditions", nargs="+", default=["swarm", "single_probe", "single"])
    a = ap.parse_args()
    jobs = [(s, c, a.budget) for s in range(1, a.seeds + 1) for c in a.conditions]
    with Pool(min(os.cpu_count() or 1, len(jobs))) as p:
        res = p.map(job, jobs)
    rows = [r for rs, _ in res for r in rs]
    metas = [m for _, m in res]
    if rows:
        save_csv(rows, "results/twoarm.csv")
    json.dump(metas, open("results/twoarm_meta.json", "w"), indent=1)
    print(f"saved results/twoarm.csv ({len(rows)} rows) and results/twoarm_meta.json")
    _report(metas, a.conditions)
