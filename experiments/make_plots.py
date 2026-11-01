"""The one results summary and the slide figures. Run from the repo root after export_sweep.py:
    python experiments/make_plots.py results/sweep

Reads the sweep tables from the folder given (default results/sweep) and the side experiments from
results/ (task.csv, knockout.csv, summary_dynamics.md, summary_vision.md, provenance/provenance.md).
Writes summary.md and the figures into that folder and, when it is not results/ itself, the same
summary.md and figures into results/, so the two summaries are one source.

Every cell is a median over runs with a bootstrap 95% confidence interval of the median (2000
resamples, fixed seed, so reruns print the same intervals) and its n; rates are k/n (percent).
"Failures we found" lists every setting where the swarm misses (wrong structure in some run, damage
not noticed, a false alarm, or a median over MISS_MM) or a baseline's median beats the swarm's;
"Ties" lists pooled settings where a baseline's interval overlaps the swarm's.
"""
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

R = sys.argv[1] if len(sys.argv) > 1 else "results/sweep"
SIDE = "results"
OUTS = [R] + ([SIDE] if os.path.normpath(R) != os.path.normpath(SIDE) else [])
# reference categorical slots in fixed order, entity bound (validated: dataviz validate_palette.js);
# mlp, only ever on the learning chart, is a neutral baseline grey rather than a fifth hue
COL = {"swarm": "#2a78d6", "single": "#eb6834", "single_probe": "#1baf7a", "pipeline": "#eda100", "mlp": "#8a8984"}
NAME = {"swarm": "BodyScout swarm", "single": "Single agent (chain model)", "single_probe": "Single agent (probes channels)",
        "pipeline": "Fixed pipeline (same parts)", "mlp": "Single agent (neural net)"}
SHORT = {"swarm": "swarm", "single": "single", "single_probe": "single_probe", "pipeline": "pipeline", "mlp": "mlp"}
INK, QUIET, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
MISS_MM = 10.0     # a swarm median reach error above this counts as a miss in the failures table
BOOT = 2000
FRESH = 101        # seeds from here on were added after the swarm v2 fixes: the independent check
FAULT_ORDER = ["none", "wrong_finding", "bad_llm", "modeler_crash", "noisy_channel"]
# Why a baseline ties or beats the swarm, by experiment. Written after reading the frozen numbers;
# printed only for experiments that have a row in the failures or ties tables.
WHY = {
    "bodies": "On clean bodies the swarm spends 32 of its 64 motions on single channel sweeps (home and bent pose "
              "for every channel) where single_probe and the pipeline spend 16, so it fits on fewer mixed motions. "
              "Its extra probes buy robustness to a bad finding (see the fault table), not accuracy on a clean body.",
    "faults": "Under no fault, bad_llm (where single_probe has no slot for the bad source) and the clean seeds of "
              "each fault, the same extra probe motions cost the swarm a few tenths of a millimetre. noisy_channel "
              "corrupts every sweep of one channel, the review's third pose included, so replication cannot outvote "
              "it; a single agent that never trusts a sweep is not misled by it.",
    "noise": "Camera noise hits every sweep the same way, so more sweeps per channel do not help, and the swarm has "
             "fewer mixed motions to average the noise down; at high noise the monitor can also raise false alarms.",
    "learning": "On known arms (no structure to discover) the single agent fits every motion with one chain model "
                "from the first batch; the swarm holds a quarter of its motions out for validation and crowns a model "
                "only when both validators agree, so early on it has no model or a model fit on fewer motions.",
    "damage": "The single agents refit on every motion and so drift toward the damaged body without noticing it; "
              "the swarm waits for two surprises, starts a new epoch and re-probes every channel, which costs motions "
              "after the damage. A payload barely changes the tip, so it stays under the monitor's threshold.",
    "menagerie": "",
    "knockout": "",
}


# ---- helpers ------------------------------------------------------------------------
def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def source_note(path):
    """Where a side result comes from: the commit that last changed it, or this working tree."""
    if not os.path.exists(path):
        return None
    tracked = bool(git("ls-files", path))
    dirty = tracked and subprocess.run(["git", "diff", "--quiet", "HEAD", "--", path]).returncode != 0
    if tracked and not dirty:
        return f"`{path}`, last changed in {git('log', '-1', '--format=%h on %ad', '--date=short', '--', path)}"
    return f"`{path}`, regenerated in this working tree (code at {git('rev-parse', '--short', 'HEAD')})"


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=QUIET, labelsize=9)
    ax.grid(True, axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def save(fig, name):
    for out in OUTS:
        fig.savefig(f"{out}/{name}", facecolor="white")
    plt.close(fig)


def load(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["motions"] = int(r["motions"])
        r["reach_mm"] = float(r["reach_mm"]) if r["reach_mm"] not in ("", "nan") else np.nan
    return rows


def bands(rows, cond, key=None):
    by = defaultdict(list)
    for r in rows:
        if r["condition"] == cond and (key is None or r.get("damage") == key):
            by[r["motions"]].append(r["reach_mm"])
    xs = sorted(by)
    arr = [np.array(by[x]) for x in xs]
    med = [np.nanmedian(a) if np.isfinite(a).any() else np.nan for a in arr]
    lo = [np.nanpercentile(a, 25) if np.isfinite(a).any() else np.nan for a in arr]
    hi = [np.nanpercentile(a, 75) if np.isfinite(a).any() else np.nan for a in arr]
    return np.array(xs), np.array(med), np.array(lo), np.array(hi)


def boot_ci(v, n=BOOT, seed=0):
    """Median of the finite values and its bootstrap 95% interval; NaN (no model) runs are left out."""
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return np.nan, np.nan, np.nan
    meds = np.median(v[np.random.default_rng(seed).integers(0, len(v), (n, len(v)))], axis=1)
    lo, hi = np.percentile(meds, [2.5, 97.5])
    return float(np.median(v)), float(lo), float(hi)


def cell(v, digits=1):
    """'median [CI lo to hi] n=k', plus how many runs had no model at all."""
    v = np.asarray(v, float)
    m, lo, hi = boot_ci(v)
    gone = int(np.sum(~np.isfinite(v)))
    if not np.isfinite(m):
        return f"no model n={len(v)}"
    return (f"{m:.{digits}f} [{lo:.{digits}f} to {hi:.{digits}f}] n={len(v)}"
            + (f", {gone} no model" if gone else ""))


def rate(k, n):
    return f"{k}/{n} ({100 * k / n:.0f}%)" if n else "n/a"


failures, ties = [], []  # (where, setting, what happened, numbers)


def compare(where, setting, vals, right=None, pooled=True):
    """Log every baseline whose median beats the swarm's and every swarm miss to `failures`; on pooled
    rows also log baselines whose interval overlaps the swarm's to `ties`."""
    if "swarm" not in vals:
        return
    sw = boot_ci(vals["swarm"])
    for c in vals:
        if c == "swarm":
            continue
        b = boot_ci(vals[c])
        if not np.isfinite(b[0]):
            continue
        if not np.isfinite(sw[0]) or b[0] < sw[0]:
            sep = ("the swarm has no model yet" if not np.isfinite(sw[0])
                   else "intervals overlap" if b[2] >= sw[1] else "intervals do not overlap")
            failures.append((where, setting, f"{SHORT[c]} beats the swarm", f"{cell(vals[c])} vs swarm {cell(vals['swarm'])}; {sep}"))
        elif pooled and b[1] <= sw[2]:
            ties.append((where, setting, f"{SHORT[c]} ties the swarm", f"{cell(vals[c])} vs swarm {cell(vals['swarm'])}"))
    if right and "swarm" in right and right["swarm"][0] < right["swarm"][1]:
        k, n = right["swarm"]
        failures.append((where, setting, "swarm structure wrong", f"{n - k}/{n} runs"))
    if np.isfinite(sw[0]) and sw[0] > MISS_MM:
        failures.append((where, setting, f"swarm median over {MISS_MM:.0f} mm", cell(vals["swarm"])))


def present(rows, order=COL):
    return [c for c in order if any(r["condition"] == c for r in rows)]


def final_values(rows, cond, final, **match):
    return [r["reach_mm"] for r in rows if r["condition"] == cond and r["motions"] == final
            and all(str(r.get(k)) == str(v) for k, v in match.items())]


def seed_groups(meta):
    """(label, keep(seed)) for the original seeds and, when present, the held out seeds."""
    seeds = {int(m["seed"]) for m in meta if "seed" in m}
    out = []
    if any(s < FRESH for s in seeds):
        out.append((f"original seeds 1 to {max(s for s in seeds if s < FRESH)}", lambda s: int(s) < FRESH))
    if any(s >= FRESH for s in seeds):
        out.append((f"independent seeds {FRESH} to {max(seeds)}", lambda s: int(s) >= FRESH))
    return out or [("all seeds", lambda s: True)]


def table(head, rows_):
    return ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows_]


def wrap_title(ax, text, size=10.5):
    ax.set_title(text, loc="left", fontsize=size, color=INK)


# ---- header ---------------------------------------------------------------------------
head = git("rev-parse", "--short", "HEAD")
dirty = " plus uncommitted changes" if git("status", "--porcelain", "--", "experiments", "bodyscout") else ""
sweep_path = os.path.join(SIDE, "sweep.jsonl")
sweep_note = ""
if os.path.exists(sweep_path):
    blob = open(sweep_path, "rb").read()
    n_lines = blob.count(b"\n")
    sweep_note = (f" Sweep: `{sweep_path}`, {n_lines} job lines, sha256 "
                  f"{hashlib.sha256(blob).hexdigest()[:12]}.")
summary = ["# BodyScout results summary", "",
           f"Generated {date.today().isoformat()} by `experiments/make_plots.py {R}` at commit {head}{dirty}.{sweep_note} "
           f"This file and `{os.path.join(R, 'summary.md')}` are the same file; the slides quote only numbers in it.", "",
           f"Cells: median [bootstrap 95% CI of the median, {BOOT} resamples] n = runs. Rates: k/n (percent). Reach "
           "error is the median miss on held-out reachable targets, in mm, scored on the true body.", "",
           "**Read this first.** The swarm v2 fixes (two channel agents per channel probing from different poses, a "
           "review agent that rechecks doubtful channels from a third pose, a second chain modeler) were designed "
           "after we saw the fault preview on seeds 1 and 2 of the gantry and SCARA families, where one wrong channel "
           f"finding or one crashed chain modeler sank the swarm. Seeds {FRESH} and up were added after those fixes "
           "and are the independent check: tables split by seed show them separately. Swarm rows without "
           "swarm_version 2 in their meta come from the swarm before the fixes.", ""]

# jobs that raised during the sweep: listed with their error, and whether a later run completed them
err_path = os.path.join(SIDE, "sweep_errors.jsonl")
if os.path.exists(err_path) and os.path.exists(sweep_path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sweep as sweep_jobs  # noqa: E402  (the job list, so stale keys from older sweeps are left out)
    current = {k for _, _, k in sweep_jobs.build_jobs(list(sweep_jobs.DO), True)}
    done_keys = {json.loads(line)["key"] for line in open(sweep_path) if line.strip()}
    errs = {}
    for line in open(err_path):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r["key"] in current:
            errs[r["key"]] = r["error"].strip().splitlines()[-1]
    summary += ["## Jobs that errored during the sweep", ""]
    if errs:
        summary += table(["job", "error", "status"], [[k, e, "completed on a rerun after the fix below"
                                                       if k in done_keys else "MISSING from these results"]
                                                      for k, e in errs.items()])
        summary += ["", "Cause and fix: scipy's SVD failed inside a validator's replay refit, and `Validator._replay` "
                    "had no guard, so one numerical failure ended the whole run. A replay that fails now counts as a "
                    "failed check (that candidate cannot be crowned). The fix changes only runs in which a replay "
                    "failed, so every job that had already completed is unchanged; only the jobs above were rerun.", ""]
    else:
        summary += ["None.", ""]

# ---- 1. unknown body types ----------------------------------------------------------
if os.path.exists(f"{R}/bodies.csv"):
    rows = load(f"{R}/bodies.csv")
    meta = json.load(open(f"{R}/bodies_meta.json"))
    conds = present(rows)
    fams = [f for f in ("arm", "gantry", "scara", "telescope") if any(r["family"] == f for r in rows)]
    final = max(r["motions"] for r in rows)
    totals = {}
    for label, keep in seed_groups(meta):
        g_rows = [r for r in rows if keep(r["seed"])]
        g_meta = [m for m in meta if keep(m["seed"])]
        body = []
        for f in fams + ["all"]:
            match = {} if f == "all" else {"family": f}
            vals = {c: final_values(g_rows, c, final, **match) for c in conds}
            ms = {c: [m for m in g_meta if m["condition"] == c and (f == "all" or m["family"] == f)] for c in conds}
            right = {c: (sum(m["structure_correct"] for m in ms[c]), len(ms[c])) for c in conds}
            body.append([f] + [rate(*right[c]) for c in conds] + [cell(vals[c]) for c in conds])
            compare(f"bodies, {label}", f, vals, right, pooled=f == "all")
            if f == "all":
                totals[label] = right
        summary += [f"## 1. Unknown body types, {label}", "",
                    f"Told nothing about the body. Structure right = every joint's type and axis; reach error at {final} motions.", ""]
        summary += table(["body"] + [f"{SHORT[c]} structure right" for c in conds] + [f"{SHORT[c]} reach mm" for c in conds], body)
        summary.append("")
    fig, ax = plt.subplots(figsize=(7.6, 4.6), dpi=160)
    style(ax)
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    ax.grid(False, axis="y")
    offs = dict(zip(conds, np.linspace(-0.3, 0.3, len(conds))))  # y is inverted: first condition on top
    for yi, f in enumerate(fams):
        for c in conds:
            v = np.array(final_values(rows, c, final, family=f))
            med = np.nanmedian(v) if np.isfinite(v).any() else np.nan
            ax.scatter(v, [yi + offs[c]] * len(v), s=12, color=COL[c], alpha=0.35, lw=0)
            ax.scatter([med], [yi + offs[c]], s=64, color=COL[c], edgecolor="white", lw=1.5, zorder=3,
                       label=NAME[c] if yi == 0 else None)
            ax.annotate(f"{med:.1f}", (med, yi + offs[c]), xytext=(7, 0), textcoords="offset points",
                        va="center", fontsize=7.5, color=INK)
    ax.set_yticks(range(len(fams)), [f.capitalize() for f in fams], color=INK, fontsize=9.5)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel(f"reach error after {final} motions, mm (log); big dot = median, small = each robot, all seeds",
                  color=QUIET, fontsize=9)
    lines = []
    for label, right in totals.items():
        lines.append(f"{label}: " + ", ".join(f"{SHORT[c]} {right[c][0]}/{right[c][1]}" for c in conds))
    wrap_title(ax, "Told nothing about the body, robots whose full structure was found:\n" + "\n".join(lines), 9.5)
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
    fig.tight_layout()
    save(fig, "fig_bodies.png")

# ---- 2. real arms (Menagerie) ---------------------------------------------------------
if os.path.exists(f"{R}/menagerie_meta.json"):
    meta = json.load(open(f"{R}/menagerie_meta.json"))
    conds = [c for c in COL if any(m["condition"] == c for m in meta)]
    body = []
    for arm in dict.fromkeys(m["arm"] for m in meta):
        for ch in ("ordered", "shuffled"):
            vals, joints = {}, {}
            for c in conds:
                ms = [m for m in meta if m["arm"] == arm and m["channels"] == ch and m["condition"] == c]
                vals[c] = [m["final_reach_mm"] for m in ms]
                joints[c] = (f"{rate(sum(m['joints_right'] for m in ms), sum(m['n'] for m in ms))}; observable "
                             f"{sum(m['observable_right'] for m in ms)}/{sum(m['n_observable'] for m in ms)}")
            body.append([arm, ch] + [cell(vals[c]) for c in conds] + [joints[c] for c in conds])
            compare("menagerie", f"{arm} {ch}", vals)
    summary += ["## 2. Real arms from MuJoCo Menagerie, body type unknown", "",
                "Channels in the robot's own order and shuffled. Joints right counts every joint over the seeds; "
                "observable = joints whose type the fingertip can reveal.", ""]
    summary += table(["arm", "channels"] + [f"{SHORT[c]} reach mm" for c in conds] + [f"{SHORT[c]} joints right" for c in conds], body)
    summary.append("")

# ---- 3. damage ----------------------------------------------------------------------
if os.path.exists(f"{R}/damage.csv"):
    rows = load(f"{R}/damage.csv")
    kinds = sorted({r["damage"] for r in rows})
    meta = json.load(open(f"{R}/damage_meta.json"))
    conds = present(rows)
    final = max(r["motions"] for r in rows)
    at = sorted({mm.get("damaged_at", 48) for mm in meta})
    fams = sorted({mm["family"] for mm in meta if "family" in mm})
    watchers = [c for c in ("swarm", "pipeline") if c in conds]  # conditions with a monitor
    fig, axes = plt.subplots(1, len(kinds), figsize=(3.0 * len(kinds), 3.7), dpi=160, sharey=True)
    axes = np.atleast_1d(axes)
    body, det_tot = [], {c: [0, 0] for c in watchers}
    ends = {}
    for ax, k in zip(axes, kinds):
        style(ax)
        for c in conds:
            x, m, lo, hi = bands(rows, c, k)
            ok = np.isfinite(m)
            ax.fill_between(x[ok], lo[ok], hi[ok], color=COL[c], alpha=0.12, lw=0)
            ax.plot(x[ok], m[ok], "-", color=COL[c], lw=2, label=NAME[c])
        dmg = [e["motion"] for mm in meta if mm["damage"] == k and mm["condition"] == "swarm"
               for e in mm["events"] if e.get("event", "damage") == "damage"]
        d0 = int(np.median(dmg)) if dmg else at[0]
        det = []
        for c in watchers:
            ms = [mm for mm in meta if mm["damage"] == k and mm["condition"] == c]
            lat = [a - d0 for mm in ms for a in [x for x in mm["alarms"] if x >= d0][:1]]
            n_det = sum(1 for mm in ms if any(x >= d0 for x in mm["alarms"]))
            det += [rate(n_det, len(ms)), cell(lat, 0) if lat else "none detected"]
            det_tot[c][0] += n_det
            det_tot[c][1] += len(ms)
            if c == "swarm" and n_det < len(ms):
                failures.append(("damage", k, "swarm did not notice the damage", f"{len(ms) - n_det}/{len(ms)} runs"))
        ax.axvline(d0, color=QUIET, ls="--", lw=1)
        ax.text(d0 + 2, 1.25, "damage", fontsize=8, color=QUIET)
        ax.set_yscale("log")
        ax.set_ylim(1, 1000)
        ax.set_title(k.replace("_", " "), fontsize=10, color=INK, loc="left")
        ax.set_xlabel("motions", color=QUIET, fontsize=9)
        vals = {c: final_values(rows, c, final, damage=k) for c in conds}
        ends[k] = {c: boot_ci(vals[c])[0] for c in conds}
        body.append([k] + det + [cell(vals[c]) for c in conds])
        compare("damage", k, vals)
    summary += [f"## 3. Damage mid run (break at motion {'/'.join(map(str, at))}; {', '.join(fams)}, body type unknown)", "",
                "Detected = an alarm at or after the damage (alarms before it are false alarms and do not count). "
                f"Latency = motions from the damage to the first such alarm. Recovered error = reach error at {final} motions.", ""]
    head_ = ["damage"]
    for c in watchers:
        head_ += [f"{SHORT[c]} detected", f"{SHORT[c]} latency, motions"]
    summary += table(head_ + [f"{SHORT[c]} recovered error mm" for c in conds], body)
    summary += ["", "All kinds: " + "; ".join(f"{SHORT[c]} detected {rate(*det_tot[c])}" for c in watchers) + ".",
                "Gaps in the swarm curve are deliberate: between the alarm and the next crowned model the planner "
                "has no trusted model and refuses to move.", ""]
    axes[0].set_ylabel("reach error, mm (log)", color=QUIET, fontsize=9)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=8.5, loc="lower center", ncol=len(conds))
    sw = [e["swarm"] for e in ends.values()]
    best = [k.replace("_", " ") for k, e in ends.items() if all(e["swarm"] <= e[c] for c in conds)]
    fig.suptitle(f"The swarm notices the damage in {det_tot['swarm'][0]} of {det_tot['swarm'][1]} runs and ends "
                 f"{min(sw):.1f} to {max(sw):.1f} mm off (median per kind);\nit ends closest of all four on "
                 f"{len(best)} of {len(kinds)} kinds" + (f" ({', '.join(best)})" if best else ""),
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.tight_layout(rect=(0, 0.07, 1, 0.88))
    save(fig, "fig_damage.png")

# ---- 4. cube task ---------------------------------------------------------------------
task_path = f"{SIDE}/task.csv"
if os.path.exists(task_path):
    with open(task_path) as f:
        trows = list(csv.DictReader(f))
    body = []
    for c in [c for c in COL if any(r["condition"] == c for r in trows)]:
        for phase in ("before", "after"):
            xs = [r for r in trows if r["condition"] == c and r["phase"] == phase]
            if not xs:
                continue
            ok = sum(int(r["success"]) for r in xs)
            errs = [float(r["place_err_mm"]) for r in xs if r["place_err_mm"] not in ("", "nan")]
            body.append([SHORT[c], phase, rate(ok, len(xs)), cell(errs) if errs else "none placed",
                         sum(int(r["replan_requested"]) for r in xs)])
    summary += ["## 4. Cube pick and place before and after damage", "",
                f"Source: {source_note(task_path)}. One trial per arm seed; damage (long link) at motion 48. "
                "Place error is measured only where the cube was placed.", ""]
    summary += table(["condition", "phase", "success", "place error mm", "replans asked"], body)
    summary.append("")


# ---- 5 and 6. faults and noise --------------------------------------------------------
def robustness(name, setting_key, settings, group=None):
    """One row per setting pooled over families; failures also scanned per family. Returns (lines,
    {setting: {condition: per run finals}})."""
    rows = load(f"{R}/{name}.csv")
    meta = json.load(open(f"{R}/{name}_meta.json"))
    if group is not None:
        rows = [r for r in rows if group[1](r["seed"])]
        meta = [m for m in meta if group[1](m["seed"])]
    where = name if group is None else f"{name}, {group[0]}"
    conds = present(rows)
    final = max(r["motions"] for r in rows)
    settings = [s for s in settings if any(str(r[setting_key]) == s for r in rows)]
    fams = sorted({r["family"] for r in rows})
    body, by = [], {}
    for s in settings:
        for fam in [None] + fams:
            match = {setting_key: s, **({"family": fam} if fam else {})}
            vals = {c: final_values(rows, c, final, **match) for c in conds}
            ms = {c: [m for m in meta if m["condition"] == c and str(m[setting_key]) == s
                      and (fam is None or m["family"] == fam)] for c in conds}
            right = {c: (sum(m["structure_correct"] for m in ms[c]), len(ms[c])) for c in conds}
            compare(where, s + (f", {fam}" if fam else ""), vals, right, pooled=fam is None)
            if fam is not None:
                continue
            by[s] = vals
            fired = {c: any(sum((m.get("fault_hits") or {}).values()) for m in ms[c]) for c in conds}
            cells = []
            for c in conds:
                tag = " (no slot: fault never fired)" if setting_key == "fault" and s != "none" and not fired[c] else ""
                cells.append(cell(vals[c]) + tag)
            body.append([s] + cells + [rate(*right[c]) for c in conds])
    n_robots = len({(m["family"], m["seed"]) for m in meta})
    lines = table([setting_key.replace("_mm", " mm")] + [f"{SHORT[c]} reach mm" for c in conds]
                  + [f"{SHORT[c]} structure right" for c in conds], body)
    probes = {c: [m["probe_motions"] for m in meta if m["condition"] == c and m.get("probe_motions") is not None] for c in conds}
    lines += ["", "Probe motions per run (single channel sweeps among the motions), all settings: "
              + "; ".join(f"{SHORT[c]} {cell(probes[c], 0)}" for c in conds if probes[c]) + "."]
    if setting_key == "noise_mm":
        fa = []
        for s in settings:
            r_ = [s]
            for c in (c for c in conds if c in ("swarm", "pipeline")):
                ms = [m for m in meta if m["condition"] == c and str(m[setting_key]) == s]
                k = sum(1 for m in ms if m["alarms"])
                r_.append(rate(k, len(ms)))
                if c == "swarm" and k:
                    failures.append(("noise", f"{s} mm", "swarm false alarm", f"{k}/{len(ms)} runs"))
            fa.append(r_)
        lines += ["", "False alarms (the monitor declared damage on an undamaged body), runs with any:", ""]
        lines += table(["noise mm"] + [SHORT[c] for c in conds if c in ("swarm", "pipeline")], fa)
    return [f"{n_robots} robots ({', '.join(fams)}), reach error at {final} motions.", ""] + lines + [""], by, conds


if os.path.exists(f"{R}/faults.csv"):
    fmeta = json.load(open(f"{R}/faults_meta.json"))
    panels = []
    for grp in seed_groups(fmeta):
        lines, by, conds = robustness("faults", "fault", FAULT_ORDER, grp)
        summary += [f"## 5. Injected faults, {grp[0]}", ""] + lines
        panels.append((grp[0], by, conds))
    summary += ["wrong_finding flips one channel's reported joint type (the home pose channel agent); bad_llm posts 3 "
                "confident wrong structures every epoch in an LLM's slot (the pipeline's LLM stage has the final say, so "
                "it adopts them); modeler_crash stops one chain modeler at motion 24; noisy_channel adds 20 mm noise to "
                "every sweep of one channel. Faults hit one agent instance; the swarm's replicas and second chain "
                "modeler are not faulted. 'No slot' means the condition has no place for that fault (a single agent "
                "has no findings and no hypothesis source), so it ran unchanged.", ""]
    fig, axes = plt.subplots(1, len(panels), figsize=(6.2 * len(panels), 4.4), dpi=160, sharey=True)
    axes = np.atleast_1d(axes)
    claims = []
    for ax, (label, by, conds) in zip(axes, panels):
        style(ax)
        faults = [f for f in FAULT_ORDER if f in by]
        w = 0.8 / len(conds)
        for j, c in enumerate(conds):
            for i, f in enumerate(faults):
                m, lo, hi = boot_ci(by[f][c])
                x = i + (j - (len(conds) - 1) / 2) * w
                if not np.isfinite(m):
                    ax.text(x, 1.3, "no\nmodel", ha="center", fontsize=6, color=QUIET)
                    continue
                ax.bar(x, m, width=w - 0.03, color=COL[c], label=NAME[c] if i == 0 else None, edgecolor="white", lw=1)
                ax.errorbar(x, m, yerr=[[m - lo], [hi - m]], color=INK, lw=0.8, capsize=1.5)
        ax.axhline(MISS_MM, color=QUIET, ls=":", lw=1)
        ax.text(len(faults) - 0.45, MISS_MM * 1.1, f"{MISS_MM:.0f} mm", fontsize=7.5, color=QUIET, ha="right")
        ax.set_xticks(range(len(faults)), [f.replace("_", "\n") for f in faults], fontsize=8.5, color=INK)
        ax.set_yscale("log")
        ax.set_ylim(0.5, 400)
        ok = {c: [f for f in faults if f != "none" and boot_ci(by[f][c])[0] <= MISS_MM] for c in conds}
        n_f = len([f for f in faults if f != "none"])
        ax.set_title(label + f"\nmedian under {MISS_MM:.0f} mm on " + ", ".join(f"{SHORT[c]} {len(ok[c])}/{n_f}" for c in conds)
                     + " faults", loc="left", fontsize=9, color=INK)
        claims.append((label, ok, n_f))
    axes[0].set_ylabel("median reach error at 64 motions, mm (log)\nbar = median, whisker = 95% CI", color=QUIET, fontsize=9)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=8.5, loc="lower center", ncol=len(h))
    label, ok, n_f = claims[-1]
    missed = [f for f in FAULT_ORDER[1:] if f not in ok["swarm"]]
    fig.suptitle(f"One bad part: the swarm stays under {MISS_MM:.0f} mm on {len(ok['swarm'])} of {n_f} faults on the "
                 f"independent seeds" + (f" (not {', '.join(missed)})" if missed else "") + "; "
                 + ", ".join(f"{SHORT[c]} on {len(ok[c])}" for c in ok if c != "swarm"),
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.tight_layout(rect=(0, 0.07, 1, 0.92))
    save(fig, "fig_faults.png")

if os.path.exists(f"{R}/noise.csv"):
    lines, by, conds = robustness("noise", "noise_mm", ["1", "2", "5", "10"])
    summary += ["## 6. Camera noise sweep", ""] + lines
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    style(ax)
    levels = [s for s in ("1", "2", "5", "10") if s in by]
    for j, c in enumerate(conds):
        st = [boot_ci(by[s][c]) for s in levels]
        xs = np.array([float(s) for s in levels]) * (1 + 0.025 * (j - 1.5))
        m = np.array([v[0] for v in st])
        ax.errorbar(xs, m, yerr=[m - [v[1] for v in st], [v[2] for v in st] - m], color=COL[c], lw=2, marker="o",
                    ms=6, capsize=2, label=NAME[c], markeredgecolor="white")
        ax.annotate(f"{m[-1]:.1f}", (xs[-1], m[-1]), xytext=(8, 0), textcoords="offset points", va="center",
                    fontsize=8, color=INK)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks([float(s) for s in levels], [f"{s} mm" for s in levels])
    ax.set_xlabel("camera noise (std per axis)", color=QUIET, fontsize=9)
    ax.set_ylabel("median reach error at 64 motions, mm (log)", color=QUIET, fontsize=9)
    top = levels[-1]
    wrap_title(ax, "Median reach error at 64 motions, whisker = 95% CI\n"
               f"at {top} mm camera noise: " + ", ".join(f"{SHORT[c]} {boot_ci(by[top][c])[0]:.1f}" for c in conds)
               + f"\nat {levels[0]} mm: " + ", ".join(f"{SHORT[c]} {boot_ci(by[levels[0]][c])[0]:.1f}" for c in conds), 9.5)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    save(fig, "fig_noise.png")

# ---- 7. knockout ----------------------------------------------------------------------
ko_path = f"{SIDE}/knockout.csv"
if os.path.exists(ko_path):
    krows = load(ko_path)
    kmeta = json.load(open(f"{SIDE}/knockout_meta.json"))
    final = max(r["motions"] for r in krows)
    kconds = list(dict.fromkeys(m["condition"] for m in kmeta))
    full = boot_ci(final_values(krows, "full collective", final))[0]
    body = []
    for c in kconds:
        v = final_values(krows, c, final)
        ms = [m for m in kmeta if m["condition"] == c]
        med = boot_ci(v)[0]
        body.append([c, rate(sum(m["structure_correct"] for m in ms), len(ms)), cell(v),
                     "" if c == "full collective" else f"{med - full:+.1f}",
                     sum(1 for x in v if not np.isfinite(x)), sum(m["disagreements"] for m in ms)])
    at_ = sorted({e["motion"] for m in kmeta for e in m.get("knockout", [])})
    summary += ["## 7. Knockout: one agent type removed mid run", "",
                f"Source: {source_note(ko_path)}. Removed at motion {at_[0] if at_ else '?'}; unknown bodies "
                f"({', '.join(sorted({m['family'] for m in kmeta}))}).", ""]
    summary += table(["removed", "structure right", f"reach at {final} motions mm", "change vs full, mm",
                      "runs with no model", "validator disagreements"], body)
    summary.append("")

# ---- 8. extrapolation -----------------------------------------------------------------
if os.path.exists(f"{R}/extrapolation.json"):
    ex = json.load(open(f"{R}/extrapolation.json"))
    fams = sorted({o["family"] for o in ex if "family" in o})
    body, rates_ = [], {}
    for f in [None] + fams:
        part = [o for o in ex if f is None or o.get("family") == f]
        for kind in ("reachable", "out_of_reach"):
            xs = [o for o in part if o["target"] == kind]
            k = sum(o["refused"] for o in xs)
            body.append([f or "all", kind.replace("_", " "), rate(k, len(xs)), cell([o["naive_miss_mm"] for o in xs], 0)])
            rates_[(f or "all", kind)] = (k, len(xs))
    summary += ["## 8. Knowing when it is guessing (extrapolation guard)", "",
                "Out of reach targets sit 1.3x beyond the largest possible reach. Refused = the planner declined; "
                "naive miss = how far a planner without the guard ends from the target.", ""]
    summary += table(["family", "targets", "BodyScout refused", "naive planner miss mm"], body)
    summary.append("")
    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=160)
    style(ax)
    groups = ["all"] + fams
    for j, (kind, colr) in enumerate((("out_of_reach", COL["swarm"]), ("reachable", "#86b6ef"))):
        for i, g in enumerate(groups):
            k, n = rates_[(g, kind)]
            x = i + (j - 0.5) * 0.38
            ax.bar(x, 100 * k / n, width=0.34, color=colr, edgecolor="white", lw=1,
                   label=("out of reach targets" if kind == "out_of_reach" else "reachable targets") if i == 0 else None)
            ax.text(x, 100 * k / n + 2, f"{100 * k / n:.0f}%", ha="center", fontsize=7.5, color=INK)
    ax.set_xticks(range(len(groups)), [g.capitalize() for g in groups], color=INK, fontsize=9)
    ax.set_ylim(0, 112)
    ax.set_ylabel("targets refused, %", color=QUIET, fontsize=9)
    ko, kr = rates_[("all", "out_of_reach")], rates_[("all", "reachable")]
    naive = boot_ci([o["naive_miss_mm"] for o in ex if o["target"] == "out_of_reach"])[0]
    wrap_title(ax, f"It refuses {100 * ko[0] / ko[1]:.0f}% of out of reach targets and {100 * kr[0] / kr[1]:.0f}% of "
                   f"reachable ones;\na planner without the guard misses out of reach targets by {naive:.0f} mm (median)", 10)
    ax.legend(frameon=False, fontsize=8.5, loc="upper right", bbox_to_anchor=(1, 1.02))
    fig.tight_layout()
    save(fig, "fig_extrapolation.png")

# ---- 9. learning curve on known arms ---------------------------------------------------
if os.path.exists(f"{R}/learning.csv"):
    rows = load(f"{R}/learning.csv")
    conds = present(rows)
    arms = sorted({r["arm"] for r in rows})
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    style(ax)
    tab = {}
    for c in conds:
        x, m, lo, hi = bands(rows, c)
        ok = np.isfinite(m)
        ax.fill_between(x[ok], lo[ok], hi[ok], color=COL[c], alpha=0.12, lw=0)
        ax.plot(x[ok], m[ok], "-o", color=COL[c], lw=2, ms=4, label=NAME[c], markeredgecolor="white")
        ax.annotate(f"{m[ok][-1]:.1f} mm", (x[ok][-1], m[ok][-1]), xytext=(6, {"swarm": 7, "single": -7}.get(c, 0)),
                    textcoords="offset points", va="center", fontsize=8.5, color=INK)
    body = []
    for xm in sorted({r["motions"] for r in rows}):
        vals = {c: final_values(rows, c, xm) for c in conds}
        tab[xm] = {c: boot_ci(vals[c])[0] for c in conds}
        body.append([xm] + [cell(vals[c]) for c in conds])
        compare("learning", f"{xm} motions", vals)
    summary += [f"## 9. Learning curve on known arms ({len(arms)} arms, structure known: nothing to discover)", "",
                "The honest baseline comparison: when there is no structure to find, a single agent fitting every motion "
                "is as good or better.", ""]
    summary += table(["motions"] + [f"{SHORT[c]} reach mm" for c in conds], body)
    summary.append("")
    ax.set_yscale("log")
    ax.set_xlabel("motions spent (robot budget)", color=QUIET, fontsize=9.5)
    ax.set_ylabel("reach error on unseen targets, mm (log)", color=QUIET, fontsize=9.5)
    last = max(tab)
    wrap_title(ax, f"Known arms, nothing to discover: after {last} motions " + ", ".join(
        f"{SHORT[c]} {tab[last][c]:.1f} mm" for c in conds) + f".\n{len(arms)} arms, same budget; band = interquartile range", 10)
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    fig.tight_layout()
    save(fig, "fig_learning.png")

# ---- 10. cost --------------------------------------------------------------------------
costs = []
for name in ("bodies", "damage", "faults", "noise", "learning", "menagerie"):
    if os.path.exists(f"{R}/{name}_meta.json"):
        for m in json.load(open(f"{R}/{name}_meta.json")):
            if "agent_cpu_s" in m:
                costs.append((name, m["condition"], m.get("motions_used"), m["agent_cpu_s"], m.get("probe_motions")))
if costs:
    body = []
    for name in dict.fromkeys(c[0] for c in costs):
        for cond in [c for c in COL if any(x[0] == name and x[1] == c for x in costs)]:
            xs = [x for x in costs if x[0] == name and x[1] == cond]
            mot = [x[2] for x in xs if x[2] is not None]
            probe = [x[4] for x in xs if x[4] is not None]
            body.append([name, SHORT[cond], cell(mot, 0) if mot else "n/a", cell(probe, 0) if probe else "n/a",
                         cell([x[3] for x in xs])])
    summary += ["## 10. Cost per robot (one run = one robot)", "",
                "Motions spent, of them single channel sweeps, and agent CPU seconds (process CPU in agent steps, "
                "scoring excluded; runs without the field predate it).", ""]
    summary += table(["experiment", "condition", "motions used", "probe motions", "agent CPU s"], body)
    summary.append("")

# ---- 11. provenance ---------------------------------------------------------------------
prov = f"{SIDE}/provenance/provenance.md"
if os.path.exists(prov):
    text = open(prov).read()
    final_part = text.split("## Final champion of each run", 1)
    summary += ["## 11. Provenance of crowned champions", "", f"Source: {source_note(prov)} (from the saved blackboards; "
                "per champion rows in `results/provenance/champions.csv`).", "",
                text.split("\n\n")[1] if "\n\n" in text else "", ""]
    if len(final_part) == 2:
        summary += ["Final champion of each run:", "", final_part[1].strip(), ""]

# ---- 12. dynamics and vision -------------------------------------------------------------
for path, title, note in ((f"{SIDE}/summary_dynamics.md", "12. Dynamics", "These runs use the swarm before the v2 "
                           "fixes (they predate them) and were not rerun."),
                          (f"{SIDE}/summary_vision.md", "13. Vision", "Camera perception only; independent of the swarm "
                           "version.")):
    if os.path.exists(path):
        body = re.sub(r"^(#+) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", open(path).read(), flags=re.M)
        summary += [f"## {title}", "", f"Source: {source_note(path)}. {note}", "", body.strip(), ""]

# ---- failures and ties ------------------------------------------------------------------
summary += ["## Failures we found", "",
            "Numbers are reach error in mm, median [95% CI] n. Every setting where the swarm misses (wrong structure in "
            f"some run, damage not noticed, a false alarm, or a median over {MISS_MM:.0f} mm) or a baseline's median beats "
            "the swarm's. Rows per family are included for faults and noise.", ""]
summary += table(["experiment", "setting", "what happened", "numbers"], failures) if failures else ["None in these results."]
summary += ["", "## Ties", "", "Pooled settings where a baseline's median is not better than the swarm's but its 95% "
            "interval overlaps the swarm's: the data cannot tell them apart.", ""]
summary += table(["experiment", "setting", "what happened", "numbers"], ties) if ties else ["None in these results."]
hit = list(dict.fromkeys(w.split(",")[0] for w, *_ in failures + ties if "beats" in _[1] or "ties" in _[1]))
why = [f"- **{w}**: {WHY[w]}" for w in hit if WHY.get(w)]
if why:
    summary += ["", "## Why a baseline ties or beats the swarm", ""] + why
summary.append("")

for out in OUTS:
    open(f"{out}/summary.md", "w", encoding="utf-8").write("\n".join(summary))
print("\n".join(summary))
