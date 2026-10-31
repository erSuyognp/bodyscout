"""Experiment 3 (Kitchin's open problem 2): does the planner know when it is guessing?
Half the targets are reachable, half lie beyond the arm. A naive planner executes every plan;
BodyScout refuses when its champion says the target is out of reach or the answer is unexplored."""
import os

# Pin BLAS/OpenMP to one thread before numpy or scipy load: threaded reductions sum in a
# varying order, which makes least squares fits differ run to run.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import json
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bodyscout.planning import plan, solve_ik  # noqa: E402
from bodyscout.swarm import run  # noqa: E402
from bodyscout.world import BlackBoxRobot, random_arm, reachable_targets  # noqa: E402

out = []
for s in range(1, 4):
    robot = BlackBoxRobot(random_arm(s), seed=s)
    res = run(robot, "swarm", budget=48, eval_at=(48,), n_targets=6, seed=s, use_llm=False)
    model = res["champion"]["_model"]
    Qseen = np.array([q for q, _ in robot.log])
    reach = reachable_targets(robot, 10, s + 50)
    reach_max = sum(robot.spec.links) + 0.05
    rng = np.random.default_rng(s)
    far = rng.normal(size=(10, 3))
    far = far / np.linalg.norm(far, axis=1, keepdims=True) * reach_max * 1.3
    for kind, T in (("reachable", reach), ("out_of_reach", far)):
        for i, t in enumerate(T):
            q, info = plan(model, t, robot.n_channels, Qseen, robot.limits, seed=i)
            q_naive, _ = solve_ik(model, t, robot.n_channels, robot.limits, seed=i)
            out.append({"arm": s, "target": kind, "refused": info["refused"] is not None,
                        "naive_miss_mm": float(np.linalg.norm(robot.true_tip(q_naive) - t)) * 1000})
os.makedirs("results", exist_ok=True)
json.dump(out, open("results/extrapolation.json", "w"), indent=1)
for kind in ("reachable", "out_of_reach"):
    xs = [o for o in out if o["target"] == kind]
    print(f"{kind:13s} refused {np.mean([o['refused'] for o in xs]) * 100:5.1f}%   "
          f"naive planner median miss {np.median([o['naive_miss_mm'] for o in xs]):7.1f} mm")
