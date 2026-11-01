"""The full sweep, meant for a many-core cloud VM (not a laptop): every experiment at a larger scale,
all jobs in one process pool across every CPU core.

Resumable: each finished job appends one JSON line to results/sweep.jsonl (key, settings, curve rows,
meta, seconds). On restart, jobs whose key is already in the file are skipped, so a killed or
preempted run just needs the same command again. Runs are deterministic, so a resumed sweep gives
the same numbers as an uninterrupted one. A job that raises goes to results/sweep_errors.jsonl and
is retried on the next start.

  python experiments/sweep.py --dry-run          # list the jobs, run nothing
  python experiments/sweep.py                    # everything, all cores
  python experiments/sweep.py --only bodies damage --procs 32

Jobs (LLM hypothesizers off everywhere, so the sweep needs no API key and stays deterministic):
  bodies         swarm vs pipeline vs single vs single_probe, unknown body, 4 families x 10 seeds
  damage         swarm vs pipeline vs single vs single_probe, unknown body, 6 damage kinds x 4 families x 5 robots
  faults         swarm, pipeline, single_probe, single; unknown body, 4 families x 5 seeds x every fault in
                 bodyscout/faults.py (and none, the baseline on the same robots)
  noise          the same four conditions and robots at 1, 2, 5 and 10 mm camera noise
  learning       swarm, single, mlp on 10 arms, structure known
  extrapolation  swarm, unknown body, 4 families x 5 robots; refusal rate + naive miss
  menagerie      swarm vs single on the real arms, channels ordered and shuffled
                 (needs third_party/mujoco_menagerie, see bodyscout/menagerie.py; or --no-menagerie)

Seeds 101 and up (FRESH_SEEDS, in bodies and faults) were added after the replicated findings, review
agent and second chain modeler were designed against the 1 to 10 preview: they are the independent check.
Swarm job keys carry |swarm=v<SWARM_VERSION>; bumping it reruns every swarm job (old lines stay in the
file but no job matches them, so export ignores them).

Every run-based job records motions_used, probe_motions and agent_cpu_s (process CPU seconds in agent steps, scoring
excluded). Swarm and pipeline runs of damage, faults and noise also save their blackboard to
results/blackboards/<key>.jsonl.gz for experiments/provenance_stats.py (--no-blackboards to skip).
"""
import os

# Pin BLAS/OpenMP to one thread before numpy or scipy load: threaded reductions sum in a
# varying order, which makes least squares fits differ run to run. It also stops 64 workers
# each spawning 64 BLAS threads.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import json
import sys
import time
import traceback
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bodies  # noqa: E402
import menagerie_arms  # noqa: E402
from common import job as arm_job  # noqa: E402

from bodyscout.faults import FAULTS  # noqa: E402
from bodyscout.menagerie import ARMS, ROOT as MENAGERIE_ROOT  # noqa: E402
from bodyscout.planning import plan, solve_ik  # noqa: E402
from bodyscout.swarm import run  # noqa: E402
from bodyscout.world import DAMAGES, FAMILIES, SLIDE_RANGE, BlackBoxRobot, random_body, reachable_targets  # noqa: E402

BODIES = dict(seeds=10, budget=64)
DAMAGE = dict(robots=5, at=64, budget=128)  # damage after the channel agents have had time to find the body
LEARNING = dict(arms=10, budget=64, checkpoints=(8, 12, 16, 24, 32, 48, 64, 96, 128))
EXTRAP = dict(robots=5, budget=64, n_targets=10)
MENAGERIE = dict(seeds=3, budget=160)
SWARM_VERSION = 2   # 2: replicated channel findings, review agent, second chain modeler
FRESH_SEEDS = range(101, 106)
FAULT_RUNS = dict(seeds=5, budget=64)
NOISE = dict(seeds=5, budget=64, levels_mm=(1, 2, 5, 10))
UNKNOWN_BODY_CONDITIONS = ("swarm", "pipeline", "single_probe", "single")
# an environment variable, not a flag read here: spawned workers re-import this file
BLACKBOARDS = None if os.environ.get("BODYSCOUT_NO_BLACKBOARDS") else "results/blackboards"
# rough relative cost, only used to start the longest jobs first so no core idles at the end
COST = {"menagerie": 6, "damage": 4, "learning": 2, "bodies": 2, "extrapolation": 2, "faults": 2, "noise": 2}


def build_jobs(only, menagerie):
    jobs = []
    if "bodies" in only:
        jobs += [("bodies", {"family": f, "seed": s, "condition": c})
                 for f in FAMILIES for s in [*range(1, BODIES["seeds"] + 1), *FRESH_SEEDS]
                 for c in ("swarm", "single", "single_probe", "pipeline")]
    if "damage" in only:
        jobs += [("damage", {"family": f, "seed": s, "damage": k, "condition": c})
                 for f in FAMILIES for s in range(1, DAMAGE["robots"] + 1) for k in DAMAGES
                 for c in ("swarm", "single", "single_probe", "pipeline")]
    if "faults" in only:
        jobs += [("faults", {"family": f, "seed": s, "fault": k, "condition": c})
                 for f in FAMILIES for s in [*range(1, FAULT_RUNS["seeds"] + 1), *FRESH_SEEDS] for k in FAULTS
                 for c in UNKNOWN_BODY_CONDITIONS]
    if "noise" in only:
        jobs += [("noise", {"family": f, "seed": s, "noise_mm": mm, "condition": c})
                 for f in FAMILIES for s in range(1, NOISE["seeds"] + 1) for mm in NOISE["levels_mm"]
                 for c in UNKNOWN_BODY_CONDITIONS]
    if "learning" in only:
        jobs += [("learning", {"arm": s, "condition": c})
                 for s in range(1, LEARNING["arms"] + 1) for c in ("swarm", "single", "mlp")]
    if "extrapolation" in only:
        jobs += [("extrapolation", {"family": f, "seed": s})
                 for f in FAMILIES for s in range(1, EXTRAP["robots"] + 1)]
    if "menagerie" in only and menagerie:
        jobs += [("menagerie", {"arm": a, "seed": s, "condition": c, "channels": ch})
                 for a in ARMS for s in range(1, MENAGERIE["seeds"] + 1) for c in ("swarm", "single")
                 for ch in ("ordered", "shuffled")]
    return [(exp, p, key_of(exp, p)) for exp, p in sorted(jobs, key=lambda j: -COST[j[0]])]


def key_of(exp, p):
    key = exp + "|" + "|".join(f"{k}={v}" for k, v in p.items())
    if p.get("condition", "swarm") == "swarm":  # extrapolation has no condition: it is a swarm job
        key += f"|swarm=v{SWARM_VERSION}"
    return key


# ---- one function per experiment; each returns (curve rows, meta) ----------------------------

def do_bodies(p):
    return bodies.job((p["family"], p["seed"], p["condition"], BODIES["budget"], False))


def save_blackboard(p, out, exp):
    """Swarm and pipeline boards, for provenance_stats.py. Named by job key, so a rerun overwrites."""
    if BLACKBOARDS and p["condition"] in ("swarm", "pipeline"):
        os.makedirs(BLACKBOARDS, exist_ok=True)
        name = key_of(exp, p).replace("|", "__").replace("=", "-")
        out["blackboard"].to_jsonl(os.path.join(BLACKBOARDS, name + ".jsonl.gz"))


def run_meta(out):
    """What every run-based job records about its cost and its board."""
    bb = out["blackboard"]
    return {"motions_used": out["motions"], "probe_motions": out["probe_motions"],
            "agent_s": out["agent_s"], "agent_cpu_s": out["agent_cpu_s"],
            "fault_hits": out["fault_hits"], "champions": len(bb.of("champion", epoch=-1)),
            "disagreements": len(bb.of("disagreement", epoch=-1))}


def do_damage(p):
    fam, seed, kind = p["family"], p["seed"], p["damage"]
    robot = BlackBoxRobot(random_body(seed, fam), seed=seed)
    truth = robot.spec.tokens()
    b = DAMAGE["budget"]
    out = run(robot, p["condition"], budget=b, eval_at=tuple(range(8, b + 1, 8)), n_targets=8, seed=seed,
              damage=(DAMAGE["at"], kind), max_ticks=800, use_llm=False, unknown_body=True)
    rows = [{"motions": m, "reach_mm": e} for m, e in out["curve"]]
    found = ((out["champion"] or {}).get("describe") or {}).get("structure")
    meta = {"truth": truth, "found": found, "alarms": out["alarms"], "events": out["events"],
            "damaged_at": DAMAGE["at"], **run_meta(out)}
    save_blackboard(p, out, "damage")
    return rows, meta


def unknown_body_run(p, exp, budget, obs_noise=0.002, faults=None):
    """One unknown body run for the faults and noise jobs; the truth is read here, for scoring only."""
    fam, seed = p["family"], p["seed"]
    robot = BlackBoxRobot(random_body(seed, fam), obs_noise=obs_noise, seed=seed)
    truth = robot.spec.tokens()
    out = run(robot, p["condition"], budget=budget, eval_at=tuple(range(8, budget + 1, 4)), n_targets=8,
              seed=seed, use_llm=False, unknown_body=True, faults=faults)
    found = ((out["champion"] or {}).get("describe") or {}).get("structure")
    rows = [{"motions": m, "reach_mm": e} for m, e in out["curve"]]
    meta = {"truth": truth, "found": found, "structure_correct": found == truth,
            "types_correct": found is not None and [t[0] for t in found] == [t[0] for t in truth],
            "alarms": out["alarms"], "fault_channel": seed % robot.n_channels, **run_meta(out)}
    save_blackboard(p, out, exp)
    return rows, meta


def do_faults(p):
    return unknown_body_run(p, "faults", FAULT_RUNS["budget"], faults=p["fault"])


def do_noise(p):
    return unknown_body_run(p, "noise", NOISE["budget"], obs_noise=p["noise_mm"] / 1000)


def do_learning(p):
    kw = {"budget": LEARNING["budget"], "eval_at": tuple(c for c in LEARNING["checkpoints"] if c <= LEARNING["budget"]),
          "n_targets": 8, "use_llm": False}
    return arm_job((p["arm"], p["condition"], kw))


def do_extrapolation(p):
    """Same test as experiments/extrapolation.py, on every family. Far targets sit 1.3x beyond the
    largest possible reach: base height + every link + full travel of every slide."""
    fam, s = p["family"], p["seed"]
    robot = BlackBoxRobot(random_body(s, fam), seed=s)
    res = run(robot, "swarm", budget=EXTRAP["budget"], eval_at=(EXTRAP["budget"],), n_targets=6, seed=s,
              use_llm=False, unknown_body=True)
    if res["champion"] is None:
        return [], {"no_champion": True}
    model = res["champion"]["_model"]
    Qseen = np.array([q for q, _ in robot.log])
    reach_max = 0.05 + sum(robot.spec.links) + SLIDE_RANGE * robot.spec.types.count("s")
    rng = np.random.default_rng(s)
    far = rng.normal(size=(EXTRAP["n_targets"], 3))
    far = far / np.linalg.norm(far, axis=1, keepdims=True) * reach_max * 1.3
    rows = []
    for kind, T in (("reachable", reachable_targets(robot, EXTRAP["n_targets"], s + 50)), ("out_of_reach", far)):
        for i, t in enumerate(T):
            q, info = plan(model, t, robot.n_channels, Qseen, robot.limits, seed=i)
            q_naive, _ = solve_ik(model, t, robot.n_channels, robot.limits, seed=i)
            rows.append({"target": kind, "refused": info["refused"] is not None,
                         "naive_miss_mm": float(np.linalg.norm(robot.true_tip(q_naive) - t)) * 1000})
    return rows, {"reach_max_m": reach_max, "motions_used": res["motions"], "agent_cpu_s": res["agent_cpu_s"]}


def do_menagerie(p):
    return menagerie_arms.job((p["arm"], p["seed"], p["condition"], MENAGERIE["budget"], p["channels"] == "shuffled"))


DO = {"bodies": do_bodies, "damage": do_damage, "learning": do_learning,
      "extrapolation": do_extrapolation, "menagerie": do_menagerie, "faults": do_faults, "noise": do_noise}


def work(job):
    exp, p, key = job
    t0 = time.time()
    try:
        rows, meta = DO[exp](p)
        if p.get("condition", "swarm") == "swarm":
            meta["swarm_version"] = SWARM_VERSION
        return {"key": key, "exp": exp, "params": p, "rows": rows, "meta": meta,
                "seconds": round(time.time() - t0, 1)}
    except Exception:
        return {"key": key, "exp": exp, "params": p, "error": traceback.format_exc(),
                "seconds": round(time.time() - t0, 1)}


def plain(o):
    """json default: numpy scalars and arrays to Python."""
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def load_done(path):
    """Finished keys and their run times. A line cut off by a kill mid write is ignored (and rerun)."""
    done = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done[r["key"]] = (r["exp"], r["seconds"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return done


def fmt(sec):
    sec = int(sec)
    return f"{sec // 3600}h{sec % 3600 // 60:02d}m" if sec >= 3600 else f"{sec // 60}m{sec % 60:02d}s"


def eta(todo, times, procs):
    """Remaining wall time: each job's expected seconds (mean of finished jobs of its experiment,
    else of all finished jobs) summed and spread over the workers."""
    allt = [t for ts in times.values() for t in ts]
    if not allt:
        return None
    mean = {e: np.mean(ts) for e, ts in times.items() if ts}
    return sum(mean.get(e, np.mean(allt)) for e in todo) / procs


if __name__ == "__main__":  # Windows and forkserver spawn workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", default=list(DO), choices=list(DO))
    ap.add_argument("--procs", type=int, default=os.cpu_count())
    ap.add_argument("--out", default="results/sweep.jsonl")
    ap.add_argument("--no-menagerie", action="store_true", help="skip the real arms")
    ap.add_argument("--dry-run", action="store_true", help="list the jobs and exit")
    ap.add_argument("--no-blackboards", action="store_true", help="do not save swarm and pipeline boards")
    a = ap.parse_args()
    if a.no_blackboards:  # workers inherit the environment when the pool spawns them
        os.environ["BODYSCOUT_NO_BLACKBOARDS"] = "1"
        BLACKBOARDS = None

    menagerie = "menagerie" in a.only and not a.no_menagerie
    if menagerie and not os.path.isdir(MENAGERIE_ROOT):
        sys.exit(f"Menagerie arms not found at {MENAGERIE_ROOT}. Clone them (bodyscout/menagerie.py "
                 "docstring has the command) or pass --no-menagerie.")
    jobs = build_jobs(a.only, menagerie)
    done = load_done(a.out)
    todo = [j for j in jobs if j[2] not in done]
    counts = {e: sum(j[0] == e for j in jobs) for e in DO}
    print(f"{len(jobs)} jobs ({', '.join(f'{e} {n}' for e, n in counts.items() if n)}), "
          f"{len(jobs) - len(todo)} already in {a.out}, {len(todo)} to run on {a.procs} processes")
    if a.dry_run:
        for _, _, k in todo:
            print("  " + k)
        sys.exit(0)
    if not todo:
        sys.exit(0)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    err_path = os.path.splitext(a.out)[0] + "_errors.jsonl"
    times = {e: [] for e in DO}
    for exp, sec in done.values():
        times[exp].append(sec)
    left = [j[0] for j in todo]
    t0, n_err = time.time(), 0
    with Pool(min(a.procs, len(todo))) as pool, open(a.out, "a") as out, open(err_path, "a") as err:
        for i, r in enumerate(pool.imap_unordered(work, todo, chunksize=1), 1):
            left.remove(r["exp"])
            if "error" in r:
                n_err += 1
                err.write(json.dumps(r, default=plain) + "\n")
                err.flush()
                print(f"[{i}/{len(todo)}] FAILED {r['key']}: {r['error'].strip().splitlines()[-1]}", flush=True)
                continue
            out.write(json.dumps(r, default=plain) + "\n")
            out.flush()
            os.fsync(out.fileno())  # a preempted VM loses at most the jobs still running
            times[r["exp"]].append(r["seconds"])
            e = eta(left, times, min(a.procs, len(todo)))
            print(f"[{i}/{len(todo)}] {r['key']}  {r['seconds']:.0f}s  elapsed {fmt(time.time() - t0)}  "
                  f"ETA {fmt(e) if e is not None else '?'}", flush=True)
    print(f"done in {fmt(time.time() - t0)}; {n_err} failed (see {err_path}, rerun to retry)" if n_err
          else f"done in {fmt(time.time() - t0)}, all jobs in {a.out}")
