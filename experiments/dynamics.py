"""Experiment: hidden dynamics change mid run. Does the shape Monitor notice? Does the DynamicsMonitor
notice sooner, and can it say what changed?

In sample: 3 arms + 2 SCARAs (seeds 1-3, 1-2; the monitor was tuned once on these). Out of sample: 10 new
bodies (arms 101-105, SCARAs 101-103, telescopes 101-102) plus 5 undamaged bodies (arms 106-107, SCARAs
104-105, telescope 103) for false alarms; no setting was changed for or after these. Body type is unknown
to the swarm. At motion 48 the robot gets payload_dyn (+0.35 kg) or weak_motor (one joint kp x 0.5), or
nothing (kind "none"). Two conditions, identical swarm except the monitor:
  shape    : existing shape Monitor (static sentinel moves, 1 motion each)
  dynamics : DynamicsMonitor (short fast sentinel trajectory, 0.5 motions each)
Both swarms run the Exciter + DynamicsModeler, so pre-damage budgets and models match.

    python experiments/dynamics.py              # in sample runs -> dynamics.json, figure, summary
    python experiments/dynamics.py --set oos    # out of sample runs -> dynamics_oos.json, summary
    python experiments/dynamics.py --plot       # only redraw figure and summary from the json files

LLM hypothesizers (Claude, Gemini) join the swarm for every provider with a key in .env, which makes runs
non deterministic. Add --no-llm for bit-for-bit reproducible runs.
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
from bodyscout.env import load_env  # noqa: E402
from bodyscout.swarm import make_swarm  # noqa: E402
from bodyscout.world import random_body  # noqa: E402

BODIES = [("arm", 1), ("arm", 2), ("arm", 3), ("scara", 1), ("scara", 2)]          # in sample
OOS_BODIES = ([("arm", s) for s in range(101, 106)] + [("scara", s) for s in range(101, 104)]
              + [("telescope", s) for s in (101, 102)])                              # out of sample, damaged
OOS_CLEAN = [("arm", 106), ("arm", 107), ("scara", 104), ("scara", 105), ("telescope", 103)]  # undamaged
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
    fam, seed, kind, cond, at, after, max_ticks, use_llm = args
    t0 = time.time()
    if use_llm is not False:
        load_env()  # API keys from .env; one LLM hypothesizer per provider with a key
    robot = DynamicRobot(random_body(seed, fam), dyn_seed=seed, seed=seed)
    n = robot.n_channels
    agents = make_swarm(robot, seed, use_llm=use_llm, monitor=False, channels=True)
    llm_names = [a.name for a in agents if type(a).__name__ == "LLMHypothesizer"]
    agents += [Exciter(robot, seed), DynamicsModeler(n, seed=seed)]
    agents.append(Monitor(robot, seed=seed) if cond == "shape" else DynamicsMonitor(robot, seed=seed))
    bb, rng = Blackboard(), np.random.default_rng(seed)
    damaged_at, desc, true_info, scored, alarms, seen = None, None, {}, None, [], 0
    for t in range(max_ticks):
        if damaged_at is None and robot.motions >= at:
            scored = score_models(robot, bb)
            kp0 = list(robot.spec.kp)
            # kind "none": nothing changes; the same moment still opens the same watch window
            desc = robot.damage(kind, seed) if kind != "none" else "none (undamaged)"
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
           # undamaged: every alarm in the whole run is false
           "false_alarms": len(alarms) if kind == "none" else sum(not a["after_damage"] for a in alarms),
           "detected": first is not None and kind != "none",
           "motions_to_detect": (first["motion"] - damaged_at) if first else None,
           "weak_channel": true_info.get("weak_channel"), "seconds": round(time.time() - t0, 1),
           "llm_agents": llm_names,
           "llm_hypotheses": sum(1 for h in bb.of("hypothesis", epoch=-1) if h.author in llm_names)}
    if first is not None and cond == "dynamics" and kind != "none":
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


def rate(k, n):
    return f"{k}/{n}"


def detection_stats(rows):
    """Per (kind, monitor): detected, n, median motions to detect, false alarms, cause right, payload right."""
    out = {}
    for kind in KINDS:
        for cond in CONDS:
            rs = [r for r in rows if r["kind"] == kind and r["condition"] == cond]
            det = [r for r in rs if r["detected"]]
            out[kind, cond] = {
                "n": len(rs), "det": len(det),
                "mtd": float(np.median([r["motions_to_detect"] for r in det])) if det else None,
                "fa": sum(r["false_alarms"] for r in rs),
                "cause": sum(bool(r.get("cause_right")) for r in det),
                "pay": sum(bool(r.get("payload_right")) for r in det)}
    return out


def llm_note(res):
    names = sorted({n for r in res["rows"] for n in r.get("llm_agents", [])})
    if not names:
        return "LLM hypothesizers: off (deterministic runs)."
    n_h = sum(r.get("llm_hypotheses", 0) for r in res["rows"])
    return (f"LLM hypothesizers: on ({', '.join(names)}); {n_h} LLM hypotheses posted across "
            f"{len(res['rows'])} runs. Runs are not deterministic.")


def section(res, bodies, level="##"):
    """The three summary_dynamics tables for one set of runs."""
    rows, scores = [r for r in res["rows"] if r["kind"] != "none"], res["scores"]
    st = detection_stats(rows)
    L = [f"Bodies: {', '.join(f'{f}{s}' for f, s in bodies)}. {llm_note(res)}", "",
         f"{level}# Detection", "",
         "| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for kind in KINDS:
        for cond in CONDS:
            x = st[kind, cond]
            if cond == "dynamics":
                cr = rate(x["cause"], x["n"])
                pr = rate(x["pay"], x["n"]) if kind == "payload_dyn" else "n/a"
            else:
                cr, pr = "does not name causes", "n/a"
            name = "shape Monitor" if cond == "shape" else "DynamicsMonitor"
            L.append(f"| {kind} | {name} | {rate(x['det'], x['n'])} | {fmt(x['mtd'])} | {x['fa']} | {cr} | {pr} |")
    L += ["", f"{level}# Every run", "",
          "| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        cause = r.get("cause") or ("n/a" if r["condition"] == "shape" else "missed")
        if cause == "weak_motor":
            cause = f"weak motor {r['channel']} (truth {r['weak_channel']})"
        elif r["kind"] == "weak_motor" and cause == "payload":
            cause = f"payload (truth: weak motor {r['weak_channel']})"
        elif r["kind"] == "payload_dyn" and cause == "weak_motor":
            cause = "weak motor (truth: payload)"
        L.append(f"| {r['body']} | {r['damage']} | {r['condition']} | "
                 f"{fmt(r['motions_to_detect']) if r['detected'] else 'not detected'} | {cause} | "
                 f"{fmt(r.get('payload_added_kg'), 3) if r['kind'] == 'payload_dyn' and r.get('cause') else 'n/a'} | "
                 f"{fmt(r.get('kp_ratio'), 2) if r.get('cause') == 'weak_motor' else 'n/a'} | {r['false_alarms']} |")
    sc = [(r["body"], sc_) for r, sc_ in zip(res["rows"], scores)
          if r["condition"] == "dynamics" and r["kind"] == "payload_dyn"]
    L += ["", f"{level}# Tip path error on fast moves, before damage (vs noise free truth)", "",
          "| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |",
          "| --- | --- | --- | --- | --- |"]
    for b, x in sc:
        if x is None:
            L.append(f"| {b} | no dynamics model by motion {res['args']['at']} | n/a | n/a | n/a |")
        else:
            L.append(f"| {b} | {x['shape_only_mm']:.1f} | {x['learned_mm']:.1f} | {x['est_payload_kg']:.3f} | {x['true_payload_kg']:.3f} |")
    return L


def compare(res_in, res_oos):
    """In sample vs out of sample, side by side, and a plain list of what got worse."""
    a = detection_stats([r for r in res_in["rows"] if r["kind"] != "none"])
    b = detection_stats([r for r in res_oos["rows"] if r["kind"] != "none"])
    L = ["### In sample vs out of sample", "",
         "| metric | in sample | out of sample |", "| --- | --- | --- |"]
    worse = []

    def row(label, x, y, kx, ky, higher_better=True):
        L.append(f"| {label} | {x} | {y} |")
        if kx is None or ky is None:
            return
        if (ky < kx) if higher_better else (ky > kx):
            worse.append(f"{label}: {x} in sample, {y} out of sample")

    for kind in KINDS:
        for cond in CONDS:
            x, y = a[kind, cond], b[kind, cond]
            name = f"{kind}, {'shape Monitor' if cond == 'shape' else 'DynamicsMonitor'}"
            row(f"{name}: detected", rate(x["det"], x["n"]), rate(y["det"], y["n"]),
                x["det"] / max(x["n"], 1), y["det"] / max(y["n"], 1))
            row(f"{name}: median motions to detect", fmt(x["mtd"]), fmt(y["mtd"]), x["mtd"], y["mtd"], higher_better=False)
            row(f"{name}: false alarms before damage, per run", f"{x['fa']}/{x['n']} runs", f"{y['fa']}/{y['n']} runs",
                x["fa"] / max(x["n"], 1), y["fa"] / max(y["n"], 1), higher_better=False)
            if cond == "dynamics":
                row(f"{name}: cause named right", rate(x["cause"], x["n"]), rate(y["cause"], y["n"]),
                    x["cause"] / max(x["n"], 1), y["cause"] / max(y["n"], 1))
                if kind == "payload_dyn":
                    row(f"{name}: added payload within 0.1 kg", rate(x["pay"], x["n"]), rate(y["pay"], y["n"]),
                        x["pay"] / max(x["n"], 1), y["pay"] / max(y["n"], 1))
    clean = [r for r in res_oos["rows"] if r["kind"] == "none"]
    L += ["", "### Undamaged runs: false alarms over the whole run", "",
          f"Nothing is damaged; the run continues {res_oos['args']['after']} motions past motion {res_oos['args']['at']} "
          "exactly like a damaged run. Every alarm is false.", "",
          "| body | shape Monitor alarms | DynamicsMonitor alarms | motions watched |", "| --- | --- | --- | --- |"]
    for f, s in OOS_CLEAN:
        rs = {r["condition"]: r for r in clean if r["body"] == f"{f}{s}"}
        if rs:
            L.append(f"| {f}{s} | {rs['shape']['false_alarms']} | {rs['dynamics']['false_alarms']} | "
                     f"{rs['dynamics']['end_motions']:.1f} |")
    for cond, name in (("shape", "shape Monitor"), ("dynamics", "DynamicsMonitor")):
        n_fa = sum(r["false_alarms"] for r in clean if r["condition"] == cond)
        if n_fa:
            worse.append(f"{name} raised {n_fa} false alarm(s) on the 5 undamaged bodies (in sample had no undamaged runs to compare)")
    L += ["", "### What got worse out of sample", ""]
    L += [f"- {w}" for w in worse] if worse else ["- Nothing: every out of sample rate is equal to or better than in sample."]
    return L


def make_summary(res_in, res_oos=None):
    a = res_in["args"]
    L = ["# Dynamics change detection", "",
         f"Damage at motion {a['at']}: payload_dyn (+0.35 kg at the tip) or weak_motor (one joint, kp x 0.5). "
         f"Watch window after damage: {a['after']} motions. Body type unknown to the swarm. Identical swarms; only "
         "the monitor differs. A shape sentinel costs 1 motion, a dynamics sentinel (25 samples at 10 ms) costs 0.5.", "",
         "## In sample", ""]
    L += section(res_in, BODIES)
    if res_oos is not None:
        L += ["", "## Out of sample", "",
              "New bodies with seeds no experiment or test had used. DynamicsMonitor and fit settings frozen at "
              "their committed values; nothing was tuned for or after these runs."]
        L += section(res_oos, OOS_BODIES)
        L += [""] + compare(res_in, res_oos)
    L += ["", "Notes: the swarm gets one absolute reference, the servo datasheet (rotor inertia and velocity gain). "
          "Without it a payload in kilograms is unobservable from positions: scaling every mass, kp and damping "
          "together leaves every path unchanged. The added payload is estimated by refitting only the payload "
          "on the two sentinel trajectories that raised the alarm.", "",
          "Tuning disclosure: the DynamicsMonitor's settings were changed once after a first run on the in sample "
          "bodies. That run used a median baseline, a 2x / +6 mm threshold and a 10 mm kinematic gate, and "
          "detected 4/10. The fixes: a baseline that one post damage sentinel cannot inflate (a real bug: "
          "arm2's 8 to 91 mm payload jump was missed), a threshold of max(1.5x, +2.5 mm), and a 15 mm "
          "kinematic gate (arm3's shape model sat at 11 mm, so it never fitted dynamics). The shape Monitor "
          "was not changed. The in sample numbers are in sample; the out of sample section is the honest test.", ""]
    with open(f"{R}/summary_dynamics.md", "w") as f:
        f.write("\n".join(L))
    print(f"saved {R}/summary_dynamics.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", type=int, default=48)
    ap.add_argument("--after", type=int, default=40)
    ap.add_argument("--max-ticks", type=int, default=900)
    ap.add_argument("--procs", type=int, default=os.cpu_count())
    ap.add_argument("--set", choices=("in", "oos"), default="in", help="in sample or out of sample bodies")
    ap.add_argument("--plot", action="store_true", help="only redraw from the json files")
    ap.add_argument("--no-llm", action="store_true", help="no LLM hypothesizers: deterministic runs")
    a = ap.parse_args()
    out_json = f"{R}/dynamics.json" if a.set == "in" else f"{R}/dynamics_oos.json"
    use_llm = False if a.no_llm else None  # None: one LLM hypothesizer per provider with a key
    if not a.plot:
        if a.set == "in":
            jobs = [(f, s, k, c, a.at, a.after, a.max_ticks, use_llm) for f, s in BODIES for k in KINDS for c in CONDS]
        else:
            jobs = ([(f, s, k, c, a.at, a.after, a.max_ticks, use_llm) for f, s in OOS_BODIES for k in KINDS for c in CONDS]
                    + [(f, s, "none", c, a.at, a.after, a.max_ticks, use_llm) for f, s in OOS_CLEAN for c in CONDS])
        with Pool(a.procs) as p:
            out = p.map(job, jobs)
        res = {"args": vars(a), "rows": [r for r, _ in out], "scores": [s for _, s in out]}
        os.makedirs(R, exist_ok=True)
        json.dump(to_json(res), open(out_json, "w"), indent=1)
        print(f"saved {out_json}")
    res_in = json.load(open(f"{R}/dynamics.json"))
    res_oos = json.load(open(f"{R}/dynamics_oos.json")) if os.path.exists(f"{R}/dynamics_oos.json") else None
    if a.set == "in":
        make_figure(res_in)
    make_summary(res_in, res_oos)
