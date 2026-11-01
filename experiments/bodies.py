"""Experiment 4: one system for any jointed body. Arms, gantries, SCARA and telescoping robots,
and nobody tells the agents which is which. Swarm (with channel agents) vs single agent (blind
structure search), same budget. Structure accuracy is scored here, never inside an agent."""
import os

# Pin BLAS/OpenMP to one thread before numpy or scipy load: threaded reductions sum in a
# varying order, which makes least squares fits differ run to run.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import json
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import save_csv  # noqa: E402

from bodyscout.env import load_env  # noqa: E402
from bodyscout.swarm import run  # noqa: E402
from bodyscout.world import FAMILIES, BlackBoxRobot, random_body  # noqa: E402

def claude_answer(bb, truth):
    """Claude's first batch of hypotheses, scored against the hidden body. Scoring lives here, in the
    experiment, because agents must never see robot.spec."""
    hs = [h.payload for h in bb.of("hypothesis", epoch=0) if h.payload["source"] == "claude"]
    if not hs:
        return {"claude_answered": False}
    pats = [h["pattern"] for h in hs]
    return {"claude_answered": True, "claude_patterns": pats, "claude_why": hs[0].get("why", ""),
            "claude_top1": pats[0] == truth, "claude_in_top": truth in pats,
            "claude_types_top1": [t[0] for t in pats[0]] == [t[0] for t in truth]}


def job(args):
    fam, seed, cond, budget, llm = args
    robot = BlackBoxRobot(random_body(seed, fam), seed=seed)
    out = run(robot, cond, budget=budget, eval_at=tuple(range(8, budget + 1, 4)), n_targets=8, seed=seed,
              use_llm=llm, unknown_body=True)
    d = (out["champion"] or {}).get("describe") or {}
    truth = robot.spec.tokens()
    found = d.get("structure")
    cond = cond + "+claude" if llm else cond
    rows = [{"family": fam, "seed": seed, "condition": cond, "motions": m, "reach_mm": e} for m, e in out["curve"]]
    meta = {"family": fam, "seed": seed, "condition": cond, "truth": truth, "found": found,
            "types_correct": found is not None and [t[0] for t in found] == [t[0] for t in truth],
            "structure_correct": found == truth, "links_m": d.get("links_m"),
            "identifiable": d.get("identifiable"), "agent_s": out["agent_s"], "agent_cpu_s": out["agent_cpu_s"],
            "motions_used": out["motions"], "probe_motions": out["probe_motions"]}
    if llm:
        meta.update(claude_answer(out["blackboard"], truth))
    return rows, meta


if __name__ == "__main__":  # Windows spawns workers by re-importing this file
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--budget", type=int, default=64)
    ap.add_argument("--families", nargs="+", default=list(FAMILIES))
    ap.add_argument("--conditions", nargs="+", default=["swarm", "single", "single_probe"])
    ap.add_argument("--llm", action="store_true",
                    help="also run the swarm with the Claude hypothesizer (needs ANTHROPIC_API_KEY)")
    a = ap.parse_args()
    jobs = [(f, s, c, a.budget, False) for f in a.families for s in range(1, a.seeds + 1) for c in a.conditions]
    if a.llm:
        load_env()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("--llm needs ANTHROPIC_API_KEY (shell or .env)")
        os.environ.pop("GEMINI_API_KEY", None)  # Claude alone, so the comparison isolates it
        os.environ.pop("GOOGLE_API_KEY", None)
        jobs += [(f, s, "swarm", a.budget, True) for f in a.families for s in range(1, a.seeds + 1)]
    with Pool(min(os.cpu_count(), 8 if a.llm else os.cpu_count())) as p:
        res = p.map(job, jobs)
    tag = "_llm" if a.llm else ""  # keep the committed no-LLM results intact
    save_csv([r for rs, _ in res for r in rs], f"results/bodies{tag}.csv")
    json.dump([m for _, m in res], open(f"results/bodies{tag}_meta.json", "w"), indent=1)
    for c in tuple(a.conditions) + (("swarm+claude",) if a.llm else ()):
        ms = [m for _, m in res if m["condition"] == c]
        print(f"{c:12s} joint types right {sum(m['types_correct'] for m in ms)}/{len(ms)}, "
              f"full structure right {sum(m['structure_correct'] for m in ms)}/{len(ms)}")
    if a.llm:
        ms = [m for _, m in res if m["condition"] == "swarm+claude"]
        ok = [m for m in ms if m["claude_answered"]]
        print(f"\nClaude answered {len(ok)}/{len(ms)}; its first structure matched the hidden body "
              f"{sum(m['claude_top1'] for m in ok)}/{len(ok)}, any of its structures matched "
              f"{sum(m['claude_in_top'] for m in ok)}/{len(ok)}, joint types of its first right "
              f"{sum(m['claude_types_top1'] for m in ok)}/{len(ok)}")
        for m in ms:
            got = " ".join(m["claude_patterns"][0]) if m["claude_answered"] else "(no answer)"
            print(f"  {m['family']:10s} seed {m['seed']}  truth {' '.join(m['truth']):16s} claude {got:16s} "
                  f"swarm found {' '.join(m['found'] or ['-'])}  {m.get('claude_why', '')[:90]}")
