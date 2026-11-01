"""Experiment 5: no single point of failure. In unknown body mode, remove one agent type at motion 24
and compare structure accuracy and reach error with the full collective. Same robots, same budget,
same scorer; the truth is read here for scoring only, never by an agent."""
import os

# Pin BLAS/OpenMP to one thread before numpy or scipy load: threaded reductions sum in a
# varying order, which makes least squares fits differ run to run.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import json
import sys
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import save_csv  # noqa: E402

from bodyscout.agents import llm_providers  # noqa: E402
from bodyscout.env import load_env  # noqa: E402
from bodyscout.swarm import run  # noqa: E402
from bodyscout.world import FAMILIES, BlackBoxRobot, random_body  # noqa: E402

HYPS = ["hyp-channels", "hyp-prior", "hyp-library"]
CONDITIONS = {
    "full collective": [],
    "no findings hypothesizer": ["hyp-channels"],
    "no prior hypothesizer": ["hyp-prior"],
    "no library hypothesizer": ["hyp-library"],
    "one validator lost": ["validator-0"],
    "one explorer lost": ["explorer-0"],
    "no monitor": ["monitor"],
    "every hypothesizer lost": HYPS,  # extra: the chain modeler must assemble findings itself
    "one chain modeler lost": ["modeler-chain"],
    "bent pose channel agents lost": [f"channel-bent-{i}" for i in range(8)],
    "review agent lost": ["review"],
}


def job(args):
    fam, seed, cond, gone, at, budget, use_llm = args
    robot = BlackBoxRobot(random_body(seed, fam), seed=seed)
    out = run(robot, "swarm", budget=budget, eval_at=(16, 24, 32, 48, 64), n_targets=8, seed=seed,
              use_llm=use_llm, unknown_body=True, knockout=(at, gone))
    d = (out["champion"] or {}).get("describe") or {}
    bb = out["blackboard"]
    rows = [{"family": fam, "seed": seed, "condition": cond, "motions": m, "reach_mm": e} for m, e in out["curve"]]
    meta = {"family": fam, "seed": seed, "condition": cond, "removed": gone, "truth": robot.spec.tokens(),
            "found": d.get("structure"), "structure_correct": d.get("structure") == robot.spec.tokens(),
            "knockout": [e for e in out["events"] if e["event"] == "knockout"],
            "disagreements": len(bb.of("disagreement", epoch=-1)),
            "champions": len(bb.of("champion", epoch=-1))}
    return rows, meta


if __name__ == "__main__":  # Windows spawns workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--budget", type=int, default=64)
    ap.add_argument("--at", type=int, default=24, help="motion at which the agent is removed")
    ap.add_argument("--families", nargs="+", default=list(FAMILIES))
    ap.add_argument("--llm", action="store_true", help="include LLM hypothesizers (needs keys in .env)")
    a = ap.parse_args()
    conds = dict(CONDITIONS)
    use_llm = False
    if a.llm:
        load_env()
        use_llm = None  # one LLM hypothesizer per key that is set
        for p in llm_providers():
            conds[f"no {p} hypothesizer"] = [f"hyp-{p}"]
    jobs = [(f, s, c, gone, a.at, a.budget, use_llm) for c, gone in conds.items()
            for f in a.families for s in range(1, a.seeds + 1)]
    with Pool(os.cpu_count()) as p:
        res = p.map(job, jobs)
    rows = [r for rs, _ in res for r in rs]
    metas = [m for _, m in res]
    save_csv(rows, "results/knockout.csv")
    json.dump(metas, open("results/knockout_meta.json", "w"), indent=1)

    final = max(r["motions"] for r in rows)
    reach = {c: [r["reach_mm"] for r in rows if r["condition"] == c and r["motions"] == final] for c in conds}
    full = float(np.nanmedian(reach["full collective"]))
    n_runs = len(a.families) * a.seeds
    lines = [f"# Knockout: one agent type removed at motion {a.at} ({n_runs} unknown bodies: "
             f"{', '.join(a.families)} x {a.seeds} seeds)", "",
             f"| removed | structure right | median reach at {final} motions, mm | change vs full, mm | "
             "runs with no model | validator disagreements |",
             "| --- | --- | --- | --- | --- | --- |"]
    for c in conds:
        ms = [m for m in metas if m["condition"] == c]
        ok = sum(m["structure_correct"] for m in ms)
        med = float(np.nanmedian(reach[c])) if np.isfinite(reach[c]).any() else float("nan")
        no_model = sum(1 for v in reach[c] if not np.isfinite(v))
        delta = "" if c == "full collective" else f"{med - full:+.1f}"
        lines.append(f"| {c} | {ok}/{len(ms)} | {med:.1f} | {delta} | {no_model} | "
                     f"{sum(m['disagreements'] for m in ms)} |")
    if not a.llm:
        lines += ["", "LLM hypothesizers were off (no --llm), so their knockouts were not run. The "
                  "library hypothesizer has an empty library in these runs, so removing it is a no-op control."]
    open("results/knockout.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
