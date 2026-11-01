"""Experiment 6: real robot arms from MuJoCo Menagerie (6 and 7 joints), body type unknown.
Swarm (with channel agents) vs single agent, same budget, same targets. Run with channels in chain
order and with channels shuffled, since the chain model assumes channel i is the i-th joint.
Structure accuracy is scored here from the hidden spec, never inside an agent."""
import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import json
import sys
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import save_csv  # noqa: E402

from bodyscout.menagerie import MenagerieRobot  # noqa: E402
from bodyscout.swarm import run  # noqa: E402

EVAL_AT = (16, 32, 48, 64, 96, 128, 160)


def observable(robot):
    """Channels whose hinge moves the fingertip at the home pose. A wrist roll about the tool axis
    leaves a single tip point fixed, so no agent could ever tell its axis. Ground truth: scorer only."""
    d, m, s = robot._data, robot._model, robot.spec
    robot.true_tip(np.zeros(robot.n_channels))
    tip = d.site_xpos[robot._tip]
    out = []
    for c in range(s.n):
        j = s.perm[c]
        r = tip - d.xanchor[j]
        out.append(bool(np.linalg.norm(r - (r @ d.xaxis[j]) * d.xaxis[j]) > 0.01))
    return out


def job(args):
    arm, seed, cond, budget, shuffle = args
    robot = MenagerieRobot(arm, seed=seed, shuffle=shuffle)
    truth, seen = robot.spec.tokens(), observable(robot)
    out = run(robot, cond, budget=budget, eval_at=tuple(e for e in EVAL_AT if e <= budget), n_targets=8,
              seed=seed, use_llm=False, unknown_body=True)
    d = (out["champion"] or {}).get("describe") or {}
    found = d.get("structure")
    ok = [found is not None and f == t for f, t in zip(found or truth, truth)]
    tag = "shuffled" if shuffle else "ordered"
    rows = [{"arm": arm, "seed": seed, "channels": tag, "condition": cond, "motions": m, "reach_mm": e}
            for m, e in out["curve"]]
    meta = {"arm": arm, "seed": seed, "channels": tag, "condition": cond, "truth": truth, "found": found,
            "champion": (out["champion"] or {}).get("family"), "observable": seen,
            "joints_right": int(sum(ok)), "observable_right": int(sum(o for o, v in zip(ok, seen) if v)),
            "n": len(truth), "n_observable": int(sum(seen)), "structure_correct": found == truth,
            "final_reach_mm": out["curve"][-1][1], "agent_cpu_s": out["agent_cpu_s"], "motions_used": out["motions"]}
    return rows, meta


if __name__ == "__main__":  # Windows spawns workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["panda", "ur5e"])
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--budget", type=int, default=160)
    a = ap.parse_args()
    jobs = [(arm, s, c, a.budget, sh) for arm in a.arms for s in range(1, a.seeds + 1)
            for c in ("swarm", "single") for sh in (False, True)]
    with Pool(min(os.cpu_count(), len(jobs))) as p:
        res = p.map(job, jobs)
    save_csv([r for rs, _ in res for r in rs], "results/menagerie.csv")
    json.dump([m for _, m in res], open("results/menagerie_meta.json", "w"), indent=1)
    for m in res:
        m = m[1]
        print(f"{m['arm']:6s} seed {m['seed']} {m['channels']:8s} {m['condition']:6s} champion {str(m['champion']):5s} "
              f"reach {m['final_reach_mm']:7.1f} mm  joints right {m['joints_right']}/{m['n']} "
              f"(observable {m['observable_right']}/{m['n_observable']})  truth {' '.join(m['truth'])}  "
              f"found {' '.join(m['found'] or ['-'])}")
