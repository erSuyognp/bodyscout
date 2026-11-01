"""The live demo. One unknown arm, the swarm learns it, the arm gets damaged, the swarm notices
and relearns. Prints the blackboard as a story and (optionally) renders a video.

    python demo.py                       # narrated run in the terminal
    python demo.py --video demo.mp4      # also render a video for the slides / backup
    python demo.py --damage tool --arm 7 # pick another body and another injury
"""
import os

# Pin BLAS/OpenMP to one thread before numpy or scipy load: threaded reductions sum in a
# varying order, which makes least squares fits differ run to run.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse

import numpy as np

from bodyscout.env import load_env
from bodyscout.swarm import run
from bodyscout.world import FAMILIES, BlackBoxRobot, random_arm, random_body

load_env()  # API keys from .env; LLM hypothesizers switch on only for keys that are set

ap = argparse.ArgumentParser()
ap.add_argument("--arm", type=int, default=3)
ap.add_argument("--damage", default="long_link")
ap.add_argument("--family", default="arm", choices=FAMILIES,
                help="body type; anything but the default runs in unknown body mode with channel agents")
ap.add_argument("--unknown", action="store_true", help="unknown body mode even for an arm")
ap.add_argument("--at", type=int, default=48)
ap.add_argument("--budget", type=int, default=104)
ap.add_argument("--llm", action="store_true")
ap.add_argument("--video", default=None)
a = ap.parse_args()

unknown = a.unknown or a.family != "arm"
robot = BlackBoxRobot(random_body(a.arm, a.family), seed=a.arm)
print(f"\nUnknown robot with {robot.n_channels} unlabeled channels. The swarm sees nothing else.\n")
seen = set()
timeline = []  # (motion, text) for the video


def say(m, text):
    print(f"[motion {m:3d}] {text}")
    timeline.append((m, text))


def on_tick(bb, rob, t, events):
    for e in events:
        key = ("event", e["motion"])
        if key not in seen:
            seen.add(key)
            say(e["motion"], f"!! HIDDEN DAMAGE: {e['what']} (the swarm is not told)")
    for art in bb.artifacts:
        if art.id in seen:
            continue
        seen.add(art.id)
        p = art.payload
        if art.kind == "finding":
            kind = {"h": "rotates", "s": "slides", "?": "is hidden from here"}[p["type"]]
            say(rob.motions, f"{art.author}: my channel {kind}"
                             + (f" about/along {p['axis']}" if p["type"] != "?" else ""))
        elif art.kind == "hypothesis":
            say(rob.motions, f"{art.author}: maybe the body is {' '.join(p['pattern'])}")
        elif art.kind == "champion":
            d = p["describe"]
            links = ", ".join(f"{v}" if ok else "not identifiable"
                              for v, ok in zip(d.get("links_m", []), d.get("identifiable", [])))
            extra = f" structure {' '.join(d['structure'])}, links [{links}] m" if "structure" in d else ""
            say(rob.motions, f"crowned {p['family']} model ({p['votes']} validators agree), "
                             f"holdout {p['holdout_mm']:.1f} mm{extra}")
        elif art.kind == "verdict" and p["replayed"] is False:
            say(rob.motions, f"{art.author} rejected {p['family']}: failed the replay check")
        elif art.kind == "disagreement":
            say(rob.motions, f"!! {art.author}: validators disagree on the champion ({p['mine']} vs {p['theirs']})")
        elif art.kind == "anomaly":
            say(rob.motions, f"monitor: surprise {p['surprise_mm']:.0f} mm > {p['threshold_mm']:.0f} mm, "
                             f"my body changed. New epoch, relearning.")


out = run(robot, "swarm", budget=a.budget, eval_at=tuple(range(8, a.budget + 1, 8)), n_targets=8,
          seed=a.arm, damage=(a.at, a.damage), use_llm=a.llm or None, max_ticks=600, on_tick=on_tick,
          unknown_body=unknown)
print(f"\nTrue structure (hidden until now): {' '.join(robot.spec.tokens())}")
print("\nReach error on unseen targets (median, mm):")
for m, e in out["curve"]:
    bar = "#" * int(min(e, 60) / 2) if not np.isnan(e) else "(paused: no trusted model yet)"
    print(f"  {m:4d} motions  {e:6.1f}  {bar}")
out["blackboard"].to_jsonl("runs/demo_blackboard.jsonl")
print("\nProvenance DAG written to runs/demo_blackboard.jsonl")

if a.video:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter

    # replay the hidden body for drawing; after the damage motion use the damaged body
    log = robot.log
    dmg_m = out["events"][0]["motion"] if out["events"] else 10 ** 9
    damaged_spec = robot.spec
    robot_draw = BlackBoxRobot(random_body(a.arm, a.family), seed=a.arm)
    fig = plt.figure(figsize=(11, 5.2), dpi=110)
    ax3 = fig.add_subplot(1, 2, 1, projection="3d")
    axc = fig.add_subplot(1, 2, 2)
    curve = [(m, e) for m, e in out["curve"]]
    writer = FFMpegWriter(fps=8)
    with writer.saving(fig, a.video, dpi=110):
        trail = []
        for i, (q, x) in enumerate(log):
            m = i + 1
            if m == dmg_m + 1:
                robot_draw._set_spec(damaged_spec)
            sk = robot_draw.skeleton(q)
            trail.append(x)
            ax3.cla()
            ax3.plot(sk[:, 0], sk[:, 1], sk[:, 2], "-o", color="#2a5db0", lw=3, ms=4)
            tr = np.array(trail[-40:])
            ax3.scatter(tr[:, 0], tr[:, 1], tr[:, 2], s=6, color="#d9534f", alpha=0.5)
            ax3.set_xlim(-0.5, 0.5); ax3.set_ylim(-0.5, 0.5); ax3.set_zlim(0, 0.7)
            ax3.set_title(f"motion {m}" + ("   (damaged)" if m > dmg_m else ""))
            axc.cla()
            pts = [(cm, ce) for cm, ce in curve if cm <= m]
            if pts:
                axc.plot([p[0] for p in pts], [p[1] for p in pts], "-o", color="#2a5db0")
            axc.axvline(dmg_m, color="#d9534f", ls="--", lw=1)
            axc.set_xlim(0, a.budget); axc.set_ylim(0, 60)
            axc.set_xlabel("motions spent"); axc.set_ylabel("reach error on unseen targets (mm)")
            msgs = [t for tm, t in timeline if tm <= m][-4:]
            axc.set_title("\n".join(s[:70] for s in msgs), fontsize=7.5, loc="left")
            writer.grab_frame()
    print(f"video written to {a.video}")
