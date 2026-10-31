"""Planner: inverse kinematics on whatever self model is champion, with an extrapolation guard."""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares


def solve_ik(model, target, n, limits=(-2.0, 2.0), seed=0, n_cand=250, n_refine=3):
    rng = np.random.default_rng(seed)
    lo, hi = limits
    cands = rng.uniform(lo, hi, (n_cand, n))
    if hasattr(model, "sample_inverse"):  # generative model proposes many answers at once
        try:
            cands = np.vstack([cands, np.clip(model.sample_inverse(target, 64, rng), lo, hi)])
        except Exception:
            pass
    err = np.linalg.norm(model.predict(cands) - target, axis=1)
    best_q, best_e = None, np.inf
    for q0 in cands[np.argsort(err)[:n_refine]]:
        r = least_squares(lambda q: model.predict(q[None])[0] - target, q0,
                          bounds=(lo, hi), max_nfev=60, diff_step=1e-3)
        e = float(np.linalg.norm(r.fun))
        if e < best_e:
            best_q, best_e = r.x, e
    return best_q, best_e


def novelty(q, Q_seen):
    """Distance in joint space to the nearest motion the robot has actually tried."""
    if len(Q_seen) == 0:
        return np.inf
    return float(np.min(np.linalg.norm(np.asarray(Q_seen) - q, axis=1)))


def plan(model, target, n, Q_seen, limits=(-2.0, 2.0), reach_tol=0.012, novelty_tol=None, seed=0):
    """Returns (q or None, info). Refuses when the model says the target is out of reach,
    or when the answer lies far from anything the robot has explored (Kitchin's open problem 2)."""
    q, model_err = solve_ik(model, target, n, limits, seed)
    nov = novelty(q, Q_seen)
    info = {"model_err_m": model_err, "novelty_rad": nov}
    if model_err > reach_tol:
        return None, {**info, "refused": "model says unreachable"}
    if novelty_tol is not None and nov > novelty_tol:
        return None, {**info, "refused": "outside explored region"}
    return q, {**info, "refused": None}


def reach_errors(robot, model, targets, n, seed=0):
    """Score a model by what matters: true distance from target after executing its plan.
    Uses robot.true_tip, which is scoring only and never seen by agents."""
    out = []
    for i, t in enumerate(targets):
        q, _ = solve_ik(model, t, n, robot.limits, seed + i)
        out.append(float(np.linalg.norm(robot.true_tip(q) - t)))
    return np.array(out)
