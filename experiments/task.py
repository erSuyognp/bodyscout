"""Pick-and-place on a body the swarm, or one agent, had to discover.

20 trials. Each trial is one arm seed, scored before damage and again after it,
for the swarm and for the single agent. Same arms, same motion budget, same
held-out cube scene, same scorer. The scorer reads the true cube pose. The
planner is told only the Cartesian pick and place, which is the task, and it
talks to the monitor and the validators through the blackboard.

    python experiments/task.py
    python experiments/task.py --trials 1

One visible trial writes the whole blackboard, learning and task together:

    python experiments/task.py --demo --damage long_link
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

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bodyscout.blackboard import Blackboard  # noqa: E402
from bodyscout.swarm import make_swarm, run  # noqa: E402
from bodyscout.task import HIGH_MM, TaskPlanner, _commands, _plan_fields, evaluate_phase, sample_scene, score_placement  # noqa: E402
from bodyscout.world import BlackBoxRobot, Cube, CubeScene, random_arm  # noqa: E402
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


def _demo_targets(spec, seed, kind, n_cubes):
    """Pick and place points the arm can reach before and after this damage.

    The harness fits two scratch models with the true joint pattern, which agents
    never receive. The task planner is told only the Cartesian points.
    """
    from bodyscout.models import ChainModel
    from bodyscout.planning import plan

    def fit(robot, fit_seed):
        rng = np.random.default_rng(fit_seed)
        q = rng.uniform(-1.5, 1.5, (36, robot.n_channels))
        x = np.array([robot.move(qq) for qq in q])
        model = ChainModel(robot.n_channels, restarts=2, seed=fit_seed).fit(
            q, x, patterns=[robot.spec.tokens()])
        return model, q

    pre = BlackBoxRobot(spec, seed=seed)
    post = BlackBoxRobot(spec, seed=seed + 1)
    post.damage(kind, seed)
    m_pre, q_pre = fit(pre, seed + 11)
    m_post, q_post = fit(post, seed + 12)
    rng = np.random.default_rng(seed + 13)
    tips = []
    for i in range(50):
        if len(tips) >= max(n_cubes, 2):
            break
        p = np.asarray(pre.true_tip(rng.uniform(-1.5, 1.5, pre.n_channels)), float)
        if any(np.linalg.norm(p - t) < 0.08 for t in tips):
            continue
        _, pre_info = plan(m_pre, p, pre.n_channels, q_pre, pre.limits, seed=seed + i)
        _, post_info = plan(m_post, p, post.n_channels, q_post, post.limits, seed=seed + 50 + i)
        if pre_info["refused"] is None and post_info["refused"] is None:
            tips.append(p)
    if len(tips) < 2:
        return None
    while len(tips) < n_cubes:
        tips.append(tips[-1] + np.array([0.1, 0.0, 0.0]))
    return tips[0], tips[1], tips[:n_cubes]


def _dashboard_motion(bb, at_id) -> int:
    """Motion count the dashboard draws, up to and including artifact `at_id`."""
    items = [(n.id, None) for n in bb.needs] + [(a.id, a) for a in bb.artifacts]
    motions = 0
    for i, art in sorted(items, key=lambda z: z[0]):
        if art is not None and art.kind == "observation" and not art.payload.get("carried"):
            motions += 1
        if i == at_id:
            return motions
    return motions


def _check_visible(bb) -> None:
    """The log the dashboard reads has to show both the swarm and the task."""
    authors = {a.author for a in bb.artifacts} | {n.author for n in bb.needs}
    kinds = {a.kind for a in bb.artifacts}
    need_kinds = {n.kind for n in bb.needs}
    missing = []
    if "task-planner" not in authors:
        missing.append("task-planner")
    if not any(a.author == "monitor" for a in bb.artifacts):
        missing.append("monitor")
    for kind in ("plan", "replan", "command", "champion", "anomaly"):
        if kind not in kinds:
            missing.append(kind)
    for kind in ("replan", "trusted-model", "task"):
        if kind not in need_kinds:
            missing.append(f"need {kind}")
    if missing:
        raise SystemExit("task blackboard is missing " + ", ".join(missing))


def run_visible_trial(seed=1, kind="long_link", max_motions=320, max_ticks=900, n_cubes=3):
    """One pick-and-place on the swarm's blackboard, damaged after the first reach.

    The harness posts the task and applies the injury. The swarm and the task
    planner only meet through the blackboard. Returns (board, summary).
    """
    spec = random_arm(seed)
    robot = BlackBoxRobot(spec, seed=seed)
    links_before = [float(v) for v in spec.links]
    bb = Blackboard()
    agents = make_swarm(robot, seed, use_llm=False)
    rng = np.random.default_rng(seed)
    planner = TaskPlanner(_commands(robot), seed=seed)

    chosen = _demo_targets(spec, seed, kind, n_cubes)
    if chosen is None:
        picks, places = sample_scene(robot, n_cubes, seed + 20_000)
        pick, place = picks[0], places[0]
        cubes = picks
    else:
        pick, place, cubes = chosen
    scene = CubeScene([Cube(f"cube{j}", p) for j, p in enumerate(cubes)])
    starts = [c.pos.copy() for c in scene.cubes]
    robot.attach_scene(scene)
    src = bb.post("source", "scorer", {"source": "task", "trial": 0,
                                       "describes": "pick and place one cube"})
    bb.need("task", "scorer", 10.0, parents=[src.id], trial=0, cube=0,
            pick=[round(float(v), 4) for v in pick],
            place=[round(float(v), 4) for v in place])

    damage_info = None
    t = 0
    while t < max_ticks and robot.motions < max_motions:
        # The injury lands once a reach has started, before the grasp, so the
        # monitor can alarm and the planner can ask for a new champion.
        if damage_info is None and planner._plan is not None and planner._i >= 1:
            what = robot.damage(kind, seed)
            damage_info = {"motion": _dashboard_motion(bb, bb.artifacts[-1].id),
                           "what": what, "after_id": bb.artifacts[-1].id,
                           "plan_id": planner._plan.id}
        alarmed = damage_info is not None and any(
            a.kind == "anomaly" and a.id > damage_info["after_id"] for a in bb.artifacts)
        if damage_info is None or alarmed:
            planner.step(bb, t)
            recovered = (alarmed and planner._plan is not None
                         and planner._plan.id != damage_info["plan_id"]
                         and planner._i >= 1 and not planner.done and not bb.has_need("replan"))
            if recovered:
                while not planner.done and t < max_ticks and robot.motions < max_motions:
                    t += 1
                    planner.step(bb, t)
                break
            if alarmed and planner.done and planner.replanned:
                break
        for i in rng.permutation(len(agents)):
            agents[i].step(bb, t)
        t += 1

    scored = score_placement(scene, place, 0, starts)
    scored.update(_plan_fields(bb))
    result = bb.latest("result", epoch=-1)
    summary = {
        "robot": spec.name,
        "family": "arm",
        "n_channels": robot.n_channels,
        "true_structure": robot.spec.tokens(),
        "true_links_m": links_before,
        "true_links_after_m": [float(v) for v in robot.spec.links],
        "true_tool_m": float(robot.spec.tool),
        "budget": robot.motions,
        "damage": {"kind": kind, "at": None if damage_info is None else damage_info["motion"],
                   "events": [] if damage_info is None else [
                       {"motion": damage_info["motion"], "what": damage_info["what"],
                        "after_id": damage_info["after_id"]}]},
        "task": {
            "success": bool(scored["success"]),
            "place_err_mm": None if scored["place_err_mm"] is None else round(float(scored["place_err_mm"]), 2),
            "replan_requested": bool(planner.replanned),
            "grasped": bool(scored["grasped"]),
            "holding": bool(scored["holding"]),
            "others_still": bool(scored["others_still"]),
            "refused": scored.get("refused") or "",
            "model_err_mm": scored.get("model_err_mm"),
            "result_id": None if result is None else result.id,
        },
        "llm": [],
    }
    return bb, summary


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


def _write_visible(seed, kind):
    bb, summary = run_visible_trial(seed=seed, kind=kind)
    os.makedirs("runs", exist_ok=True)
    bb.to_jsonl("runs/task_blackboard.jsonl")
    with open("runs/task_summary.json", "w") as f:
        json.dump(summary, f, indent=1)
    _check_visible(bb)
    task = summary["task"]
    err = "n/a" if task["place_err_mm"] is None else f"{task['place_err_mm']:.1f} mm"
    print(f"saved runs/task_blackboard.jsonl ({len(bb.artifacts)} artifacts, {len(bb.needs)} needs)")
    print(f"saved runs/task_summary.json")
    print(f"pick-and-place {'placed' if task['success'] else 'missed'} ({err}), "
          f"replan={task['replan_requested']}, damage={summary['damage']['kind']} "
          f"at motion {summary['damage']['at']}")
    print("open http://localhost:8000/dashboard/?bb=../runs/task_blackboard.jsonl"
          "&summary=../runs/task_summary.json")
    print("serve the repo root first: python -m http.server 8000")


if __name__ == "__main__":  # Windows spawns workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true",
                    help="one pick-and-place on the swarm blackboard; write runs/task_blackboard.jsonl")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--trials", type=int, default=20, help="arm seeds; each is one pick-and-place trial")
    ap.add_argument("--conditions", nargs="+", default=["swarm", "single"])
    ap.add_argument("--budget", type=int, default=112)
    ap.add_argument("--at", type=int, default=48, help="motion count at which the arm is damaged")
    ap.add_argument("--kind", default="long_link")
    ap.add_argument("--damage", default=None, help="damage kind for --demo; defaults to --kind")
    ap.add_argument("--places", type=int, default=1, help="held-out placements per phase")
    ap.add_argument("--cubes", type=int, default=3, help="cubes in the scene; one is the target")
    a = ap.parse_args()
    if a.demo:
        _write_visible(a.seed, a.damage or a.kind)
        sys.exit(0)
    kw = {"budget": a.budget, "at": a.at, "kind": a.damage or a.kind, "places": a.places,
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
