"""Shared helpers: run many (robot, condition) jobs in parallel and save tidy CSV rows."""
import os

# Pin BLAS/OpenMP to one thread before numpy or scipy load: threaded reductions sum in a
# varying order, which makes least squares fits differ run to run.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import csv
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bodyscout.swarm import run  # noqa: E402
from bodyscout.world import BlackBoxRobot, random_arm  # noqa: E402


def job(args):
    arm_seed, cond, kw = args
    robot = BlackBoxRobot(random_arm(arm_seed), seed=arm_seed)
    out = run(robot, cond, seed=arm_seed, **kw)
    rows = [{"arm": arm_seed, "n_joints": robot.n_channels, "condition": cond, "motions": m,
             "reach_mm": e} for m, e in out["curve"]]
    meta = {"arm": arm_seed, "condition": cond, "alarms": out["alarms"], "events": out["events"],
            "champion": (out["champion"] or {}).get("describe"), "agent_s": out["agent_s"],
            "agent_cpu_s": out["agent_cpu_s"], "motions_used": out["motions"],
            "truth": robot.spec.tokens()}  # body as it is at the end of the run; scoring only
    return rows, meta


def run_jobs(jobs, procs=None):
    with Pool(procs or os.cpu_count()) as p:
        return p.map(job, jobs)


def save_csv(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
