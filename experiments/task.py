"""Pick-and-place on a body the swarm, or one agent, had to discover.

20 trials. Each trial is one arm seed, scored before damage and again after it,
for the swarm and for the single agent. Same arms, same motion budget, same
held-out cube scene, same scorer. The scorer reads the true cube pose. The
planner is told only the Cartesian pick and place, which is the task, and it
talks to the monitor and the validators through the blackboard.

    python experiments/task.py
    python experiments/task.py --trials 1
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
from statistics import median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bodyscout.swarm import run  # noqa: E402
from bodyscout.task import HIGH_MM, evaluate_phase  # noqa: E402
from bodyscout.world import BlackBoxRobot, random_arm  # noqa: E402
from common import save_csv  # noqa: E402


def surprises_from(bb) -> list:
    """Monitor anomalies, plus a validator score newer than the champion and well above it.
    Copied as plain numbers so the task board does not share the learning board's dicts."""
    out = []
    for art in bb.of("anomaly", epoch=-1):
        p = art.payload
        if float(p["surprise_mm"]) > float(p["threshold_mm"]):
            out.append({"kind": "anomaly", "author": art.author, "id": art.id, "epoch": art.epoch,
                        "payload": {"surprise_mm": float(p["surprise_mm"]),
                                    "threshold_mm": float(p["threshold_mm"]),
                                    "motion": int(p["motion"])}})
    champ = bb.latest("champion")
    if champ is None or champ.payload.get("holdout_mm") in (None, 0):
        return out
    # Only a score of this champion. Later verdicts on rejected candidates are large on
    # purpose, and treating them as surprise would throw away a model the validators crowned.
    thresh = max(4.0 * float(champ.payload["holdout_mm"]), HIGH_MM)
    later = [a for a in bb.of("score", epoch=-1)
             if a.id > champ.id and a.payload.get("champion") == champ.id
             and a.payload.get("holdout_mm") is not None
             and float(a.payload["holdout_mm"]) > thresh]
    if later:
        art = later[-1]
        out.append({"kind": art.kind, "author": art.author, "id": art.id, "epoch": art.epoch,
                    "payload": {"holdout_mm": float(art.payload["holdout_mm"]),
                                "n_holdout": int(art.payload.get("n_holdout") or 0)}})
    return out


def _public(champ):
    if not champ:
        return None
    return {"family": champ.get("family"), "holdout_mm": champ.get("holdout_mm"),
            "describe": champ.get("describe")}


def job(args):
    seed, cond, kw = args
    spec = random_arm(seed)
    robot = BlackBoxRobot(spec, seed=seed)
    out = run(robot, cond, seed=seed, budget=kw["budget"], eval_at=(kw["budget"],),
              n_targets=2, damage=(kw["at"], kw["kind"]), max_ticks=kw["max_ticks"],
              use_llm=False)
    after_surprises = surprises_from(out["blackboard"])
    phases = (("before", spec, out["champion_before"], []),
              ("after", robot.spec, out["champion"], after_surprises))
    rows = []
    for phase, body, champ, surprises in phases:
        # Same scene seed for both conditions: the arm seed and the phase, not the agent.
        scene_seed = seed + (0 if phase == "before" else 10_000)
        for scored in evaluate_phase(body, champ, surprises, scene_seed,
                                     n_trials=kw["places"], n_cubes=kw["cubes"]):
            err = scored["place_err_mm"]
            model_err = scored["model_err_mm"]
            rows.append({
                "arm": seed, "condition": cond, "phase": phase, "place": scored["trial"],
                "success": int(bool(scored["success"])),
                "place_err_mm": "" if err is None else round(float(err), 2),
                "replan_requested": int(bool(scored["replan_requested"])),
                "grasped": int(bool(scored["grasped"])),
                "holding": int(bool(scored["holding"])),
                "others_still": int(bool(scored["others_still"])),
                "model_err_mm": "" if model_err is None else round(float(model_err), 2),
                "refused": scored["refused"] or "",
            })
    meta = {"arm": seed, "condition": cond, "damage": kw["kind"], "alarms": out["alarms"],
            "events": out["events"], "champion_before": _public(out["champion_before"]),
            "champion_after": _public(out["champion"]),
            "surprises_after": [{k: s[k] for k in ("kind", "author")} for s in after_surprises]}
    return rows, meta


def _summarize(rows):
    print(f"{'condition':8} {'phase':8} {'success':>12} {'median miss':>22} {'replans':>8}")
    for cond in sorted({r["condition"] for r in rows}):
        for phase in ("before", "after"):
            xs = [r for r in rows if r["condition"] == cond and r["phase"] == phase]
            if not xs:
                continue
            ok = sum(r["success"] for r in xs)
            errs = [float(r["place_err_mm"]) for r in xs if r["place_err_mm"] != ""]
            med = median(errs) if errs else float("nan")
            replans = sum(r["replan_requested"] for r in xs)
            print(f"{cond:8} {phase:8} {ok:2d}/{len(xs):<2d} {100.0 * ok / len(xs):5.0f}%"
                  f"  {med:7.1f} mm over {len(errs):2d} measured  {replans:8d}")


if __name__ == "__main__":  # Windows spawns workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=20, help="arm seeds; each is one pick-and-place trial")
    ap.add_argument("--conditions", nargs="+", default=["swarm", "single"])
    ap.add_argument("--budget", type=int, default=112)
    ap.add_argument("--at", type=int, default=48, help="motion count at which the arm is damaged")
    ap.add_argument("--kind", default="long_link")
    ap.add_argument("--places", type=int, default=1, help="held-out placements per phase")
    ap.add_argument("--cubes", type=int, default=3, help="cubes in the scene; one is the target")
    a = ap.parse_args()
    kw = {"budget": a.budget, "at": a.at, "kind": a.kind, "places": a.places,
          "cubes": a.cubes, "max_ticks": max(400, a.budget * 8)}
    jobs = [(s, c, kw) for s in range(1, a.trials + 1) for c in a.conditions]
    with Pool(os.cpu_count()) as pool:
        res = pool.map(job, jobs)
    rows = [r for rs, _ in res for r in rs]
    metas = [m for _, m in res]
    save_csv(rows, "results/task.csv")
    os.makedirs("results", exist_ok=True)
    json.dump(metas, open("results/task_meta.json", "w"), indent=1, default=str)
    print("saved results/task.csv", len(rows), "rows")
    _summarize(rows)
