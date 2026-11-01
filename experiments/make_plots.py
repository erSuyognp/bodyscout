"""Slide figures + summary numbers from results/*.csv. Run from the repo root:
    python experiments/make_plots.py                 # results/
    python experiments/make_plots.py results/sweep   # the cloud sweep, after export_sweep.py

Headline numbers are medians over runs with a bootstrap 95% confidence interval of the median
(2000 resamples, fixed seed, so reruns print the same intervals). The last table, "Failures we found",
lists every setting where the swarm misses (wrong structure in some run, damage not noticed, or a median
reach error over MISS_MM) or a baseline's median beats the swarm's.
"""
import csv
import json
import os
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

R = sys.argv[1] if len(sys.argv) > 1 else "results"
COL = {"swarm": "#2a78d6", "pipeline": "#8b5cc4", "single_probe": "#c79a1e", "single": "#eb6834",
       "mlp": "#1baf7a"}  # fixed order, entity bound
NAME = {"swarm": "BodyScout swarm", "pipeline": "Fixed pipeline (same parts)", "single_probe": "Single agent (probes channels)",
        "single": "Single agent (chain model)", "mlp": "Single agent (neural net)"}
INK, QUIET, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
MISS_MM = 10.0     # a swarm median reach error above this counts as a miss in the failures table
BOOT = 2000
FRESH = 101        # seeds from here on were added after the swarm v2 fixes: the independent check


def seed_groups(meta):
    """(label, keep(seed)) for the preview seeds and, when present, the held out seeds."""
    seeds = {int(m["seed"]) for m in meta if "seed" in m}
    out = []
    if any(s < FRESH for s in seeds):
        out.append(("preview seeds 1 to 10", lambda s: int(s) < FRESH))
    if any(s >= FRESH for s in seeds):
        out.append((f"held out seeds {FRESH} and up, the independent check", lambda s: int(s) >= FRESH))
    return out or [("all seeds", lambda s: True)]


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=QUIET, labelsize=9)
    ax.grid(True, axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


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


def cell(v):
    """'median [CI lo to hi]', plus how many runs had no model at all."""
    m, lo, hi = boot_ci(v)
    gone = int(np.sum(~np.isfinite(np.asarray(v, float))))
    if not np.isfinite(m):
        return "no model"
    return f"{m:.1f} [{lo:.1f} to {hi:.1f}]" + (f", {gone} no model" if gone else "")


failures = []  # (where, setting, what happened, numbers)


def compare(where, setting, vals, right=None, conds=None):
    """Log to `failures` every baseline whose median beats the swarm's, and every swarm miss.
    vals: condition -> per run values (lower is better). right: condition -> (correct, runs)."""
    if "swarm" not in vals:
        return
    sw = boot_ci(vals["swarm"])
    for c in conds or [c for c in vals if c != "swarm"]:
        if c == "swarm" or c not in vals:
            continue
        b = boot_ci(vals[c])
        if np.isfinite(b[0]) and (not np.isfinite(sw[0]) or b[0] < sw[0]):
            sep = ("the swarm has no model yet" if not np.isfinite(sw[0])
                   else "intervals overlap" if b[2] >= sw[1] else "intervals do not overlap")
            failures.append((where, setting, f"{NAME.get(c, c)} beats the swarm",
                             f"{cell(vals[c])} vs swarm {cell(vals['swarm'])}; {sep}"))
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


summary = ["# BodyScout results summary", "",
           f"Cells are median reach error in mm [bootstrap 95% CI of the median, {BOOT} resamples] over runs.", "",
           "**Read this first.** The swarm v2 fixes (two channel agents per channel probing from different poses, a "
           "review agent that rechecks doubtful channels from a third pose, a second chain modeler) were designed "
           "after we saw the fault preview on seeds 1 and 2 of the gantry and SCARA families, where one wrong channel "
           f"finding or one crashed chain modeler sank the swarm. Seeds {FRESH} and up were added after those fixes "
           "and are the independent check: tables split by seed show them separately. Swarm rows without "
           "swarm_version 2 in their meta come from the swarm before the fixes.", ""]

# ---- learning curve -------------------------------------------------------------
if os.path.exists(f"{R}/learning.csv"):
    rows = load(f"{R}/learning.csv")
    conds = present(rows)
    arms = sorted({r["arm"] for r in rows})
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    style(ax)
    summary += [f"## Learning an unknown body ({len(arms)} arms, median reach error [95% CI], mm)", "",
                "| motions | " + " | ".join(NAME[c] for c in conds) + " |",
                "| --- | " + " | ".join("---" for _ in conds) + " |"]
    table = {}
    for c in conds:
        x, m, lo, hi = bands(rows, c)
        ok = np.isfinite(m)
        ax.fill_between(x[ok], lo[ok], hi[ok], color=COL[c], alpha=0.15, lw=0)
        ax.plot(x[ok], m[ok], "-o", color=COL[c], lw=2, ms=4, label=NAME[c])
        dy = {"swarm": 7, "single": -7}.get(c, 0)
        ax.annotate(f"{m[ok][-1]:.1f} mm", (x[ok][-1], m[ok][-1]), xytext=(6, dy),
                    textcoords="offset points", va="center", fontsize=8.5, color=INK)
        table[c] = dict(zip(x, zip(m, lo, hi)))
    for xm in sorted({r["motions"] for r in rows}):
        vals = {c: final_values(rows, c, xm) for c in conds}
        summary.append(f"| {xm} | " + " | ".join("no model yet" if not np.isfinite(vals[c]).any() else cell(vals[c])
                                                  for c in conds) + " |")
        compare("learning", f"{xm} motions", vals)
    ax.set_yscale("log")
    ax.set_xlabel("motions spent (robot budget)", color=QUIET, fontsize=9.5)
    ax.set_ylabel("reach error on unseen targets, mm (log)", color=QUIET, fontsize=9.5)
    # titles state what this data shows, computed here, so a rerun can never leave a stale claim
    at = max(xm for xm in table[conds[0]] if xm <= 48)
    said = [f"{NAME[c].split(' (')[-1].rstrip(')') if c != 'swarm' else 'swarm'} {table[c][at][0]:.1f} mm"
            for c in conds if at in table[c] and np.isfinite(table[c][at][0])]
    ax.set_title(f"Median reach error after {at} motions:\n" + ", ".join(said) + ".\n"
                 f"{len(arms)} unknown arms, same motion budget; band = interquartile range",
                 loc="left", fontsize=10, color=INK)
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    fig.tight_layout()
    fig.savefig(f"{R}/fig_learning.png")
    summary.append("")

# ---- damage ---------------------------------------------------------------------
if os.path.exists(f"{R}/damage.csv"):
    rows = load(f"{R}/damage.csv")
    kinds = sorted({r["damage"] for r in rows})
    meta = json.load(open(f"{R}/damage_meta.json"))
    conds = present(rows)
    final = max(r["motions"] for r in rows)
    at = sorted({mm.get("damaged_at", 48) for mm in meta})
    fams = sorted({mm["family"] for mm in meta if "family" in mm})
    fig, axes = plt.subplots(1, len(kinds), figsize=(3.0 * len(kinds), 3.6), dpi=160, sharey=True)
    axes = np.atleast_1d(axes)
    watchers = [c for c in ("swarm", "pipeline") if c in conds]  # conditions with a monitor
    summary += [f"## Damage mid run (break at motion {'/'.join(map(str, at))}"
                + (f"; {', '.join(fams)}, body type unknown" if fams else "") + ")", "",
                "| damage | " + " | ".join(f"{c} detected at (median motions after damage)" for c in watchers) + " | "
                + " | ".join(f"{NAME[c]} error at {final}, mm" for c in conds) + " |",
                "| --- | " + " | ".join("---" for _ in watchers + conds) + " |"]
    det_all = n_runs = 0
    end_by_kind = {}
    for ax, k in zip(axes, kinds):
        style(ax)
        ends = {}
        for c in conds:
            x, m, lo, hi = bands(rows, c, k)
            ok = np.isfinite(m)
            ax.fill_between(x[ok], lo[ok], hi[ok], color=COL[c], alpha=0.15, lw=0)
            ax.plot(x[ok], m[ok], "-o", color=COL[c], lw=2, ms=3, label=NAME[c])
            ends[c] = m[ok][-1]
        dmg = [e["motion"] for mm in meta if mm["damage"] == k and mm["condition"] == "swarm"
               for e in mm["events"] if e.get("event", "damage") == "damage"]
        d0 = int(np.median(dmg)) if dmg else at[0]
        det = []
        for c in watchers:
            ms = [mm for mm in meta if mm["damage"] == k and mm["condition"] == c]
            lat = [a - d0 for mm in ms for a in [x for x in mm["alarms"] if x >= d0][:1]]
            n_det = sum(1 for mm in ms if any(x >= d0 for x in mm["alarms"]))
            det.append(f"{np.median(lat) if lat else 'not detected'} ({n_det}/{len(ms)} runs)")
            if c == "swarm":
                det_all, n_runs = det_all + n_det, n_runs + len(ms)
                if n_det < len(ms):
                    failures.append(("damage", k, "swarm did not notice the damage", f"{len(ms) - n_det}/{len(ms)} runs"))
        ax.axvline(d0, color=QUIET, ls="--", lw=1)
        ax.text(d0 + 2, 1.25, "damage", fontsize=8, color=QUIET)
        ax.set_yscale("log")
        ax.set_ylim(1, max(300, np.nanmax([r["reach_mm"] for r in rows if r["damage"] == k] + [0]) * 1.2))
        ax.set_title(k.replace("_", " "), fontsize=10, color=INK, loc="left")
        ax.set_xlabel("motions", color=QUIET, fontsize=9)
        vals = {c: final_values(rows, c, final, damage=k) for c in conds}
        summary.append(f"| {k} | " + " | ".join(det) + " | " + " | ".join(cell(vals[c]) for c in conds) + " |")
        compare("damage", k, vals)
        end_by_kind[k] = ends
    axes[0].set_ylabel("reach error, mm (log)", color=QUIET, fontsize=9)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=8.5, loc="lower right", ncol=len(conds))
    sw = [e["swarm"] for e in end_by_kind.values()]
    others = [c for c in conds if c != "swarm"]
    wins = {c: [k.replace("_", " ") for k, e in end_by_kind.items() if e[c] < e["swarm"]] for c in others}
    lost = "; ".join(f"{NAME[c].lower()} ends closer on {', '.join(w)}" for c, w in wins.items() if w)
    fig.suptitle(f"The swarm notices the damage in {det_all} of {n_runs} runs and ends {min(sw):.1f} to {max(sw):.1f} mm off.\n"
                 + (lost[0].upper() + lost[1:] if lost else "The swarm ends closer than every baseline on every injury"),
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.tight_layout(rect=(0, 0.06, 1, 0.9))
    fig.savefig(f"{R}/fig_damage.png")
    summary.append("")
    summary.append("Gaps in the swarm curve are deliberate: between the alarm and the next crowned model "
                   "the planner has no trusted model and refuses to move.")
    summary.append("")

# ---- extrapolation --------------------------------------------------------------
if os.path.exists(f"{R}/extrapolation.json"):
    ex = json.load(open(f"{R}/extrapolation.json"))
    summary += ["## Knowing when it is guessing", "", "| targets | BodyScout refused | naive planner median miss, mm |",
                "| --- | --- | --- |"]
    groups = [("", ex)] + [(f + ", ", [o for o in ex if o.get("family") == f])
                           for f in sorted({o["family"] for o in ex if "family" in o})]
    for name, part in groups:
        for kind in ("reachable", "out_of_reach"):
            xs = [o for o in part if o["target"] == kind]
            summary.append(f"| {name}{kind.replace('_', ' ')} | {100 * np.mean([o['refused'] for o in xs]):.0f}% | "
                           f"{np.median([o['naive_miss_mm'] for o in xs]):.0f} |")
    summary.append("")

# ---- real arms (Menagerie) ------------------------------------------------------
if os.path.exists(f"{R}/menagerie_meta.json"):
    meta = json.load(open(f"{R}/menagerie_meta.json"))
    summary += ["## Real arms from MuJoCo Menagerie, body type unknown (median over seeds)", "",
                "| arm | channels | swarm reach, mm | single reach, mm | swarm joints right | single joints right |",
                "| --- | --- | --- | --- | --- | --- |"]
    for arm in dict.fromkeys(m["arm"] for m in meta):
        for ch in ("ordered", "shuffled"):
            cell_ = {}
            for c in ("swarm", "single"):
                ms = [m for m in meta if m["arm"] == arm and m["channels"] == ch and m["condition"] == c]
                cell_[c] = ([m["final_reach_mm"] for m in ms],
                            f"{sum(m['joints_right'] for m in ms)}/{sum(m['n'] for m in ms)} "
                            f"(observable {sum(m['observable_right'] for m in ms)}/{sum(m['n_observable'] for m in ms)})")
            summary.append(f"| {arm} | {ch} | {cell(cell_['swarm'][0])} | {cell(cell_['single'][0])} | "
                           f"{cell_['swarm'][1]} | {cell_['single'][1]} |")
            compare("menagerie", f"{arm} {ch}", {c: v[0] for c, v in cell_.items()})
    summary.append("")

# ---- unknown body types ------------------------------------------------------
if os.path.exists(f"{R}/bodies.csv"):
    rows = load(f"{R}/bodies.csv")
    meta = json.load(open(f"{R}/bodies_meta.json"))
    conds = present(rows)
    fams = [f for f in ("arm", "gantry", "scara", "telescope") if any(r["family"] == f for r in rows)]
    final = max(r["motions"] for r in rows)
    fig, ax = plt.subplots(figsize=(7.2, 1.0 + 0.6 * len(conds) * len(fams) / 2), dpi=160)
    style(ax)
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    ax.grid(False, axis="y")
    for label, keep in seed_groups(meta):
        g_rows = [r for r in rows if keep(r["seed"])]
        g_meta = [m for m in meta if keep(m["seed"])]
        summary += [f"## Unknown body types, {label} (median reach error at {final} motions [95% CI], mm; "
                    "structure found)", "",
                    "| body | " + " | ".join(NAME[c] for c in conds) + " | "
                    + " | ".join(f"{c} structure right" for c in conds) + " |",
                    "| --- | " + " | ".join("---" for _ in conds + conds) + " |"]
        for f in fams:
            vals = {c: final_values(g_rows, c, final, family=f) for c in conds}
            ms = {c: [m for m in g_meta if m["family"] == f and m["condition"] == c] for c in conds}
            right = {c: (sum(m["structure_correct"] for m in ms[c]), len(ms[c])) for c in conds}
            summary.append(f"| {f} | " + " | ".join(cell(vals[c]) for c in conds) + " | "
                           + " | ".join(f"{right[c][0]}/{right[c][1]}" for c in conds) + " |")
            compare(f"bodies, {label.split(',')[0]}", f, vals, right)
        summary.append("")
    offs = dict(zip(conds, np.linspace(0.27, -0.27, len(conds))))
    lab = {"swarm": "Swarm with channel agents", "single": "Single agent, blind structure search",
           "single_probe": "Single agent that probes channels", "pipeline": "Fixed pipeline, same parts"}
    for yi, f in enumerate(fams):
        for c in conds:
            v = final_values(rows, c, final, family=f)
            med = np.nanmedian(v) if np.isfinite(v).any() else np.nan
            ax.scatter(v, [yi + offs[c]] * len(v), s=14, color=COL[c], alpha=0.35)
            ax.scatter([med], [yi + offs[c]], s=60, color=COL[c], label=lab.get(c, NAME[c]) if yi == 0 else None, zorder=3)
    ax.set_yticks(range(len(fams)), [f.capitalize() for f in fams], color=INK, fontsize=9.5)
    ax.set_xscale("log")
    ax.set_xlabel(f"reach error after {final} motions, mm (log); big dots = median, small = each robot",
                  color=QUIET, fontsize=9)
    tot = {c: sum(m["structure_correct"] for m in meta if m["condition"] == c) for c in conds}
    n_all = sum(1 for m in meta if m["condition"] == "swarm")
    ax.set_title(f"Told nothing about the body type, the swarm finds the full structure in {tot['swarm']}/{n_all} "
                 f"robots;\n" + ", ".join(f"{lab.get(c, NAME[c]).lower()} {tot[c]}/{n_all}" for c in conds if c != "swarm"),
                 loc="left", fontsize=10.5, color=INK)
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    fig.tight_layout()
    fig.savefig(f"{R}/fig_bodies.png")


def robustness_table(name, title, setting_key, label, settings_order=None, group=None):
    """Faults and noise: one row per setting, pooled over families; failures also scanned per family.
    group: (label, keep(seed)) from seed_groups, to report preview and held out seeds apart."""
    rows = load(f"{R}/{name}.csv")
    meta = json.load(open(f"{R}/{name}_meta.json"))
    if group is not None:
        rows = [r for r in rows if group[1](r["seed"])]
        meta = [m for m in meta if group[1](m["seed"])]
        title += f", {group[0]}"
    where = name if group is None else f"{name}, {group[0].split(',')[0]}"
    conds = present(rows)
    final = max(r["motions"] for r in rows)
    settings = settings_order or sorted({str(r[setting_key]) for r in rows})
    settings = [s for s in settings if any(str(r[setting_key]) == s for r in rows)]
    fams = sorted({r["family"] for r in rows})
    out = [title.format(final=final, n=len({(m["family"], m["seed"]) for m in meta})), "",
           f"| {label} | " + " | ".join(NAME[c] for c in conds) + " | "
           + " | ".join(f"{c} structure right" for c in conds) + " |",
           "| --- | " + " | ".join("---" for _ in conds + conds) + " |"]
    for s in settings:
        for fam in [None] + fams:
            match = {setting_key: s, **({"family": fam} if fam else {})}
            vals = {c: final_values(rows, c, final, **match) for c in conds}
            ms = {c: [m for m in meta if m["condition"] == c and str(m[setting_key]) == s
                      and (fam is None or m["family"] == fam)] for c in conds}
            right = {c: (sum(m["structure_correct"] for m in ms[c]), len(ms[c])) for c in conds}
            fired = {c: any(sum((m.get("fault_hits") or {}).values()) for m in ms[c]) for c in conds}
            no_slot = {c for c in conds if setting_key == "fault" and s != "none" and not fired[c]}
            if fam is None:
                out.append(f"| {s} | " + " | ".join(cell(vals[c]) + (" (fault never fired)" if c in no_slot else "")
                                                    for c in conds) + " | "
                           + " | ".join(f"{right[c][0]}/{right[c][1]}" for c in conds) + " |")
            compare(where, f"{s}" + (f", {fam}" if fam else ""), vals, right)
    if setting_key == "noise_mm":
        out += ["", "False alarms (monitor declared damage on an undamaged body), runs with any / runs:", "",
                "| noise mm | " + " | ".join(c for c in conds if c in ("swarm", "pipeline")) + " |",
                "| --- | " + " | ".join("---" for c in conds if c in ("swarm", "pipeline")) + " |"]
        for s in settings:
            cells = []
            for c in (c for c in conds if c in ("swarm", "pipeline")):
                ms = [m for m in meta if m["condition"] == c and str(m[setting_key]) == s]
                fa = sum(1 for m in ms if m["alarms"])
                cells.append(f"{fa}/{len(ms)}")
                if c == "swarm" and fa:
                    failures.append(("noise", f"{s} mm", "swarm false alarm", f"{fa}/{len(ms)} runs"))
            out.append(f"| {s} | " + " | ".join(cells) + " |")
    return out + [""]


if os.path.exists(f"{R}/faults.csv"):
    for grp in seed_groups(json.load(open(f"{R}/faults_meta.json"))):
        summary += robustness_table(
            "faults", "## Injected faults, unknown body ({n} robots, median reach error at {final} motions [95% CI], mm)",
            "fault", "fault", ["none", "wrong_finding", "bad_llm", "modeler_crash", "noisy_channel"], group=grp)
    summary += ["wrong_finding flips one channel's reported joint type; bad_llm posts 3 confident wrong structures "
                "every epoch in an LLM's slot (the pipeline's LLM stage has the final say, so it adopts them); "
                "modeler_crash stops one chain modeler at motion 24; noisy_channel adds 20 mm noise to every sweep of "
                "one channel. Faults hit one agent instance; the swarm's replicas and second chain modeler are not "
                "faulted. 'Fault never fired' means the condition has no slot for it (a single agent has no findings "
                "and no hypothesis source), so it ran unchanged.", ""]

if os.path.exists(f"{R}/noise.csv"):
    summary += robustness_table(
        "noise", "## Camera noise sweep, unknown body ({n} robots, median reach error at {final} motions [95% CI], mm)",
        "noise_mm", "noise mm", ["1", "2", "5", "10"])

# ---- cost: motions and agent CPU per run ----------------------------------------
costs = []
for name in ("bodies", "damage", "faults", "noise", "learning"):
    if os.path.exists(f"{R}/{name}_meta.json"):
        for m in json.load(open(f"{R}/{name}_meta.json")):
            if "agent_cpu_s" in m:
                costs.append((name, m["condition"], m.get("motions_used"), m["agent_cpu_s"], m.get("probe_motions")))
if costs:
    summary += ["## Cost per run (median [95% CI]): motions spent, of them single channel sweeps, and agent CPU "
                "seconds (scoring excluded)", "",
                "| experiment | condition | runs | motions used | probe motions | agent CPU s |",
                "| --- | --- | --- | --- | --- | --- |"]
    for name in dict.fromkeys(c[0] for c in costs):
        for cond in [c for c in COL if any(x[0] == name and x[1] == c for x in costs)]:
            xs = [x for x in costs if x[0] == name and x[1] == cond]
            mot = [x[2] for x in xs if x[2] is not None]
            probe = [x[4] for x in xs if x[4] is not None]
            summary.append(f"| {name} | {cond} | {len(xs)} | {cell(mot) if mot else 'n/a'} | "
                           f"{cell(probe) if probe else 'n/a'} | {cell([x[3] for x in xs])} |")
    summary.append("")

# ---- failures -------------------------------------------------------------------
summary += ["## Failures we found", "",
            "Numbers are reach error in mm, median [95% CI]. "
            f"Every setting where the swarm misses (wrong structure in some run, damage not noticed, a false alarm, or a "
            f"median over {MISS_MM:.0f} mm) or a baseline's median beats the swarm's. Rows per family are included "
            "for faults and noise.", ""]
if failures:
    summary += ["| experiment | setting | what happened | numbers |", "| --- | --- | --- | --- |"]
    summary += [f"| {w} | {s} | {what} | {nums} |" for w, s, what, nums in failures]
else:
    summary.append("None in these results.")
summary.append("")

open(f"{R}/summary.md", "w").write("\n".join(summary))
print("\n".join(summary))
