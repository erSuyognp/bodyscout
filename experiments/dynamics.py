"""Experiment: hidden dynamics change mid run. Does the shape Monitor notice? Does the DynamicsMonitor
notice sooner, and can it say what changed?

3 arms + 2 SCARAs, body type unknown to the swarm. At motion 48 the robot gets payload_dyn (+0.35 kg)
or weak_motor (one joint kp x 0.5). Two conditions, identical swarm except the monitor:
  shape    : existing shape Monitor (static sentinel moves, 1 motion each)
  dynamics : DynamicsMonitor (short fast sentinel trajectory, 0.5 motions each)
Both swarms run the Exciter + DynamicsModeler, so pre-damage budgets and models match.

    python experiments/dynamics.py            # runs, then writes the figure and summary
    python experiments/dynamics.py --plot     # only redraw from results/dynamics.json
"""
import argparse
import json
import os
import sys

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402

import numpy as np  # noqa: E402

from bodyscout.agents import Monitor  # noqa: E402
from bodyscout.blackboard import Blackboard  # noqa: E402
from bodyscout.dynamics.agents_dyn import DynamicsModeler, DynamicsMonitor, Exciter  # noqa: E402
from bodyscout.dynamics.fit import path_rmse_mm  # noqa: E402
from bodyscout.dynamics.world_dyn import DynamicRobot  # noqa: E402
from bodyscout.swarm import make_swarm  # noqa: E402
from bodyscout.world import random_body  # noqa: E402

BODIES = [("arm", 1), ("arm", 2), ("arm", 3), ("scara", 1), ("scara", 2)]
KINDS = ("payload_dyn", "weak_motor")
CONDS = ("shape", "dynamics")
ADDED_KG, PAYLOAD_TOL_KG = 0.35, 0.10
R = "results"


def test_trajectories(n, k=3, T=60, seed=123):
    """Fast moves for scoring the models against the noise free truth (never shown to agents)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(k):
        tg, p = np.empty((T, n)), rng.uniform(-1.5, 1.5, n)
        for t in range(T):
            if t in (5, 30):
                p = rng.uniform(-1.5, 1.5, n)
            tg[t] = p
        out.append(tg)
    return out


def score_models(robot, bb):
    """Ground truth scoring at the moment of damage: shape only vs learned dynamics vs truth."""
    dms = bb.of("dynamics_model")
    champs = [a for a in bb.of("champion") if a.payload["family"] == "chain"]
    if not dms or not champs:
        return None
    dm, kin = dms[-1].payload["_model"], champs[-1].payload["_model"]
    tgs = test_trajectories(robot.n_channels)
    truth = [robot.true_trajectory(tg) for tg in tgs]
    shape = [kin.predict(tg) for tg in tgs]
    learned = [dm.predict_path(tg) for tg in tgs]
    return {"shape_only_mm": path_rmse_mm(np.array(shape), np.array(truth)),
            "learned_mm": path_rmse_mm(np.array(learned), np.array(truth)),
            "est_payload_kg": dm.params["payload"], "true_payload_kg": robot.spec.payload,
            "example": {"t": (np.arange(len(tgs[0])) + 1) * robot.dt,
                        "truth": truth[0], "shape": shape[0], "learned": learned[0]}}


def job(args):
    fam, seed, kind, cond, at, after, max_ticks = args
    t0 = time.time()
    robot = DynamicRobot(random_body(seed, fam), dyn_seed=seed, seed=seed)
    n = robot.n_channels
    agents = make_swarm(robot, seed, use_llm=False, monitor=False, channels=True)
    agents += [Exciter(robot, seed), DynamicsModeler(n, seed=seed)]
    agents.append(Monitor(robot, seed=seed) if cond == "shape" else DynamicsMonitor(robot, seed=seed))
    bb, rng = Blackboard(), np.random.default_rng(seed)
    damaged_at, desc, true_info, scored, alarms, seen = None, None, {}, None, [], 0
    for t in range(max_ticks):
        if damaged_at is None and robot.motions >= at:
            scored = score_models(robot, bb)
            kp0 = list(robot.spec.kp)
            desc = robot.damage(kind, seed)
            damaged_at = robot.motions
            weak = [i for i, (a, b) in enumerate(zip(kp0, robot.spec.kp)) if a != b]
            true_info = {"weak_channel": weak[0] if weak else None}
        for i in rng.permutation(len(agents)):
            agents[i].step(bb, t)
        anomalies = bb.of("anomaly", epoch=-1)
        for a in anomalies[seen:]:  # the budget clock is ground truth: read it from the robot
            alarms.append({"motion": robot.motions, "after_damage": damaged_at is not None,
                           **{k: v for k, v in a.payload.items() if not k.startswith("_")}})
        seen = len(anomalies)
        if damaged_at is not None and robot.motions >= damaged_at + after:
            break
    post = [a for a in alarms if a["after_damage"]]
    first = post[0] if post else None
    row = {"body": f"{fam}{seed}", "family": fam, "seed": seed, "kind": kind, "condition": cond,
           "damage": desc, "damaged_at": damaged_at, "end_motions": robot.motions, "ticks": t + 1,
           "false_alarms": sum(not a["after_damage"] for a in alarms), "detected": first is not None,
           "motions_to_detect": (first["motion"] - damaged_at) if first else None,
           "weak_channel": true_info.get("weak_channel"), "seconds": round(time.time() - t0, 1)}
    if first is not None and cond == "dynamics":
        row["cause"] = first.get("cause")
        row["channel"] = first.get("channel")
        row["payload_added_kg"] = first.get("payload_added_kg")
        row["kp_ratio"] = first.get("kp_ratio")
        row["refit_mm"] = first.get("refit_mm")
        row["cause_right"] = (first.get("cause") == "payload") if kind == "payload_dyn" else \
            (first.get("cause") == "weak_motor" and first.get("channel") == row["weak_channel"])
        if kind == "payload_dyn":
            row["payload_right"] = abs(first["payload_added_kg"] - ADDED_KG) <= PAYLOAD_TOL_KG
    dms = bb.of("dynamics_model", epoch=-1)
    row["n_dynamics_models"] = len(dms)
    return row, scored


def to_json(v):
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (np.floating, np.integer, np.bool_)):
        return v.item()
    if isinstance(v, dict):
        return {k: to_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [to_json(x) for x in v]
    return v


# ---- figure + summary ----------------------------------------------------------------
INK, QUIET, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
C_SHAPE, C_LEARN = "#eb6834", "#2a78d6"   # validated pair (dataviz validate_palette, light)


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=QUIET, labelsize=9)
    ax.grid(True, axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def make_figure(res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sc = [(r["body"], s) for r, s in zip(res["rows"], res["scores"])
          if s and r["condition"] == "dynamics" and r["kind"] == "payload_dyn"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1.35, 1]})
    fig.patch.set_facecolor(SURF)
    for ax in (a1, a2):
        style(ax)

    body, s = sc[0]
    ex = s["example"]
    truth, shape, learned = (np.array(ex[k]) for k in ("truth", "shape", "learned"))
    axis = int(np.argmax(np.ptp(truth, axis=0)))  # the coordinate that moves most
    t = np.array(ex["t"]) * 1000
    for y, col, lw, ls, lab in ((truth[:, axis], INK, 2.0, "-", "truth"),
                                (shape[:, axis], C_SHAPE, 2.0, "--", "shape only"),
                                (learned[:, axis], C_LEARN, 2.0, "-", "learned dynamics")):
        a1.plot(t, y * 1000, color=col, lw=lw, ls=ls, label=lab, zorder=3 if lab != "truth" else 2)
    a1.set_xlabel("time, ms", color=QUIET, fontsize=9)
    a1.set_ylabel(f"tip {'xyz'[axis]}, mm", color=QUIET, fontsize=9)
    a1.set_title(f"{body}: one fast move (commands jump at 50 and 300 ms)", color=INK, fontsize=10, loc="left")
    a1.legend(frameon=False, fontsize=9, labelcolor=INK, loc="best")

    names = [b for b, _ in sc]
    xs = np.arange(len(sc))
    sh = np.array([x["shape_only_mm"] for _, x in sc])
    le = np.array([x["learned_mm"] for _, x in sc])
    for i in xs:
        a2.plot([i, i], [le[i], sh[i]], color=GRID, lw=2, zorder=1)
    a2.scatter(xs, sh, s=64, color=C_SHAPE, edgecolor=SURF, lw=2, zorder=3, label="shape only")
    a2.scatter(xs, le, s=64, color=C_LEARN, edgecolor=SURF, lw=2, zorder=3, label="learned dynamics")
    for i in xs:
        a2.annotate(f"{sh[i]:.0f}", (i, sh[i]), textcoords="offset points", xytext=(9, -3), fontsize=8, color=QUIET)
        a2.annotate(f"{le[i]:.1f}", (i, le[i]), textcoords="offset points", xytext=(9, -3), fontsize=8, color=QUIET)
    a2.set_yscale("log")
    a2.set_xticks(xs, names)
    a2.set_xlim(-0.5, len(xs) - 0.3)
    a2.set_ylabel("tip path error vs truth, mm (log)", color=QUIET, fontsize=9)
    a2.set_title("Fast moves, before damage (3 test moves each)", color=INK, fontsize=10, loc="left")
    a2.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    fig.tight_layout()
    fig.savefig(f"{R}/fig_dynamics.png", dpi=180, facecolor=SURF)
    print(f"saved {R}/fig_dynamics.png")


def fmt(v, nd=1):
    return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{nd}f}"


def make_summary(res):
    rows, scores = res["rows"], res["scores"]
    L = ["# Dynamics change detection", "",
         f"Damage at motion {res['args']['at']}: payload_dyn (+0.35 kg at the tip) or weak_motor (one joint, kp x 0.5). "
         f"Bodies: {', '.join(f'{f}{s}' for f, s in BODIES)} (body type unknown to the swarm). "
         f"Watch window after damage: {res['args']['after']} motions. Identical swarms; only the monitor differs. "
         "A shape sentinel costs 1 motion, a dynamics sentinel (25 samples at 10 ms) costs 0.5.", "",
         "## Detection", "",
         "| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for kind in KINDS:
        for cond in CONDS:
            rs = [r for r in rows if r["kind"] == kind and r["condition"] == cond]
            det = [r for r in rs if r["detected"]]
            mtd = np.median([r["motions_to_detect"] for r in det]) if det else None
            fa = sum(r["false_alarms"] for r in rs)
            if cond == "dynamics":
                cr = f"{sum(bool(r.get('cause_right')) for r in det)}/{len(rs)}"
                pr = f"{sum(bool(r.get('payload_right')) for r in det)}/{len(rs)}" if kind == "payload_dyn" else "n/a"
            else:
                cr, pr = "does not name causes", "n/a"
            name = "shape Monitor" if cond == "shape" else "DynamicsMonitor"
            L.append(f"| {kind} | {name} | {len(det)}/{len(rs)} | {fmt(mtd)} | {fa} | {cr} | {pr} |")
    L += ["", "## Every run", "",
          "| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        cause = r.get("cause") or ("n/a" if r["condition"] == "shape" else "missed")
        if cause == "weak_motor":
            cause = f"weak motor {r['channel']} (truth {r['weak_channel']})"
        elif r["kind"] == "weak_motor" and cause == "payload":
            cause = f"payload (truth: weak motor {r['weak_channel']})"
        L.append(f"| {r['body']} | {r['damage']} | {r['condition']} | "
                 f"{fmt(r['motions_to_detect']) if r['detected'] else 'not detected'} | {cause} | "
                 f"{fmt(r.get('payload_added_kg'), 3) if r['kind'] == 'payload_dyn' and r.get('cause') else 'n/a'} | "
                 f"{fmt(r.get('kp_ratio'), 2) if r.get('cause') == 'weak_motor' else 'n/a'} | {r['false_alarms']} |")
    sc = [(r["body"], s) for r, s in zip(rows, scores)
          if s and r["condition"] == "dynamics" and r["kind"] == "payload_dyn"]
    L += ["", "## Tip path error on fast moves, before damage (vs noise free truth)", "",
          "| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |",
          "| --- | --- | --- | --- | --- |"]
    for b, s in sc:
        L.append(f"| {b} | {s['shape_only_mm']:.1f} | {s['learned_mm']:.1f} | {s['est_payload_kg']:.3f} | {s['true_payload_kg']:.3f} |")
    L += ["", "Notes: the swarm gets one absolute reference, the servo datasheet (rotor inertia and velocity gain). "
          "Without it a payload in kilograms is unobservable from positions: scaling every mass, kp and damping "
          "together leaves every path unchanged. The added payload is estimated by refitting only the payload "
          "on the two sentinel trajectories that raised the alarm.", "",
          "Tuning disclosure: the DynamicsMonitor's settings were changed once after a first run on these same "
          "10 bodies. That run used a median baseline, a 2x / +6 mm threshold and a 10 mm kinematic gate, and "
          "detected 4/10. The fixes: a baseline that one post damage sentinel cannot inflate (a real bug: "
          "arm2's 8 to 91 mm payload jump was missed), a threshold of max(1.5x, +2.5 mm), and a 15 mm "
          "kinematic gate (arm3's shape model sat at 11 mm, so it never fitted dynamics). The shape Monitor "
          "was not changed. Treat these numbers as in sample.", ""]
    with open(f"{R}/summary_dynamics.md", "w") as f:
        f.write("\n".join(L))
    print(f"saved {R}/summary_dynamics.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", type=int, default=48)
    ap.add_argument("--after", type=int, default=40)
    ap.add_argument("--max-ticks", type=int, default=900)
    ap.add_argument("--procs", type=int, default=os.cpu_count())
    ap.add_argument("--plot", action="store_true", help="only redraw from results/dynamics.json")
    a = ap.parse_args()
    if not a.plot:
        jobs = [(f, s, k, c, a.at, a.after, a.max_ticks) for f, s in BODIES for k in KINDS for c in CONDS]
        with Pool(a.procs) as p:
            out = p.map(job, jobs)
        res = {"args": vars(a), "rows": [r for r, _ in out], "scores": [s for _, s in out]}
        os.makedirs(R, exist_ok=True)
        json.dump(to_json(res), open(f"{R}/dynamics.json", "w"), indent=1)
        print(f"saved {R}/dynamics.json")
    res = json.load(open(f"{R}/dynamics.json"))
    make_figure(res)
    make_summary(res)
