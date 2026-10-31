"""Slide figures + summary numbers from results/*.csv. Run from the repo root:
    python experiments/make_plots.py
"""
import csv
import json
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

R = "results"
COL = {"swarm": "#2a78d6", "single": "#eb6834", "mlp": "#1baf7a"}  # fixed order, entity bound
NAME = {"swarm": "BodyScout swarm", "single": "Single agent (chain model)", "mlp": "Single agent (neural net)"}
INK, QUIET, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


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


summary = ["# BodyScout results summary", ""]

# ---- learning curve -------------------------------------------------------------
if os.path.exists(f"{R}/learning.csv"):
    rows = load(f"{R}/learning.csv")
    conds = [c for c in COL if any(r["condition"] == c for r in rows)]
    arms = sorted({r["arm"] for r in rows})
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    style(ax)
    summary += [f"## Learning an unknown body ({len(arms)} arms, median [IQR] reach error, mm)", "",
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
        cells = []
        for c in conds:
            v = table[c].get(xm)
            cells.append("no model yet" if v is None or not np.isfinite(v[0]) else f"{v[0]:.1f} [{v[1]:.1f} to {v[2]:.1f}]")
        summary.append(f"| {xm} | " + " | ".join(cells) + " |")
    ax.set_yscale("log")
    ax.set_xlabel("motions spent (robot budget)", color=QUIET, fontsize=9.5)
    ax.set_ylabel("reach error on unseen targets, mm (log)", color=QUIET, fontsize=9.5)
    ax.set_title("Chain model learners reach ~2 mm in 48 motions; a neural net is still ~12 cm off.\n"
                 "The orange spike is one unchecked bad fit the swarm's replay gate would reject",
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
    fig, axes = plt.subplots(1, len(kinds), figsize=(3.0 * len(kinds), 3.6), dpi=160, sharey=True)
    axes = np.atleast_1d(axes)
    summary += ["## Damage mid run (break at motion 48)", "",
                "| damage | swarm detected at (median motions after damage) | swarm error at end, mm | single agent error at end, mm |",
                "| --- | --- | --- | --- |"]
    for ax, k in zip(axes, kinds):
        style(ax)
        ends = {}
        for c in ("swarm", "single"):
            x, m, lo, hi = bands(rows, c, k)
            ok = np.isfinite(m)
            ax.fill_between(x[ok], lo[ok], hi[ok], color=COL[c], alpha=0.15, lw=0)
            ax.plot(x[ok], m[ok], "-o", color=COL[c], lw=2, ms=3, label=NAME[c])
            ends[c] = m[ok][-1]
        dmg = [e["motion"] for mm in meta if mm["damage"] == k and mm["condition"] == "swarm" for e in mm["events"]]
        d0 = int(np.median(dmg)) if dmg else 48
        lat = [a - d0 for mm in meta if mm["damage"] == k and mm["condition"] == "swarm"
               for a in mm["alarms"][:1]]
        ax.axvline(d0, color=QUIET, ls="--", lw=1)
        ax.text(d0 + 2, 1.25, "damage", fontsize=8, color=QUIET)
        ax.set_yscale("log")
        ax.set_ylim(1, 300)
        ax.set_title(k.replace("_", " "), fontsize=10, color=INK, loc="left")
        ax.set_xlabel("motions", color=QUIET, fontsize=9)
        n_det = sum(1 for mm in meta if mm["damage"] == k and mm["condition"] == "swarm" and mm["alarms"])
        n_all = sum(1 for mm in meta if mm["damage"] == k and mm["condition"] == "swarm")
        summary.append(f"| {k} | {np.median(lat) if lat else 'not detected'} ({n_det}/{n_all} runs) | "
                       f"{ends['swarm']:.1f} | {ends['single']:.1f} |")
    axes[0].set_ylabel("reach error, mm (log)", color=QUIET, fontsize=9)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=8.5, loc="upper right", ncol=2)
    fig.suptitle("The swarm detects 3 of 4 injuries and recovers to 2 to 3 mm; the single agent stays 25 to 44 mm off.\n"
                 "A 25 degree bent bracket goes unnoticed, so there the single agent ends closer", x=0.01, ha="left",
                 fontsize=10.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
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
    for kind in ("reachable", "out_of_reach"):
        xs = [o for o in ex if o["target"] == kind]
        summary.append(f"| {kind.replace('_', ' ')} | {100 * np.mean([o['refused'] for o in xs]):.0f}% | "
                       f"{np.median([o['naive_miss_mm'] for o in xs]):.0f} |")
    summary.append("")

open(f"{R}/summary.md", "w").write("\n".join(summary))
print("\n".join(summary))

# ---- unknown body types ------------------------------------------------------
if os.path.exists(f"{R}/bodies.csv"):
    rows = load(f"{R}/bodies.csv")
    meta = json.load(open(f"{R}/bodies_meta.json"))
    fams = [f for f in ("arm", "gantry", "scara", "telescope") if any(r["family"] == f for r in rows)]
    final = max(r["motions"] for r in rows)
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=160)
    style(ax)
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    ax.grid(False, axis="y")
    summary += [f"## Unknown body types (median reach error at {final} motions, mm; structure found)", "",
                "| body | swarm | single agent | swarm structure right | single structure right |",
                "| --- | --- | --- | --- | --- |"]
    for yi, f in enumerate(fams):
        meds = {}
        for c in ("swarm", "single"):
            v = [r["reach_mm"] for r in rows if r["family"] == f and r["condition"] == c and r["motions"] == final]
            meds[c] = np.nanmedian(v)
            ax.scatter(v, [yi + (0.12 if c == "swarm" else -0.12)] * len(v), s=14, color=COL[c], alpha=0.35)
            lab = {"swarm": "Swarm with channel agents", "single": "Single agent, blind structure search"}[c]
            ax.scatter([meds[c]], [yi + (0.12 if c == "swarm" else -0.12)], s=60, color=COL[c],
                       label=lab if yi == 0 else None, zorder=3)
        ax.plot([meds["swarm"], meds["single"]], [yi + 0.12, yi - 0.12], color=GRID, lw=1, zorder=1)
        ok = {c: sum(m["structure_correct"] for m in meta if m["family"] == f and m["condition"] == c) for c in ("swarm", "single")}
        n = sum(1 for m in meta if m["family"] == f and m["condition"] == "swarm")
        summary.append(f"| {f} | {meds['swarm']:.1f} | {meds['single']:.1f} | {ok['swarm']}/{n} | {ok['single']}/{n} |")
    ax.set_yticks(range(len(fams)), [f.capitalize() for f in fams], color=INK, fontsize=9.5)
    ax.set_xscale("log")
    ax.set_xlabel(f"reach error after {final} motions, mm (log); big dots = median, small = each robot",
                  color=QUIET, fontsize=9)
    ax.set_title("Told nothing about the body type, the swarm's channel agents find the structure;\n"
                 "a single agent searching blind usually lands on the wrong one", loc="left", fontsize=10.5, color=INK)
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    fig.tight_layout()
    fig.savefig(f"{R}/fig_bodies.png")
    summary.append("")
    open(f"{R}/summary.md", "w").write("\n".join(summary))
    print("\n".join(summary[-(len(fams) + 4):]))
