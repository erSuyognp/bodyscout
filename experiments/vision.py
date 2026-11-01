"""V3: the swarm learns an unknown body from two cameras instead of a marker. Run on the Brev GPU instance:

    MUJOCO_GL=egl python experiments/vision.py [--seeds 2] [--budget 64] [--procs 12]

Conditions, all in unknown body mode with the same swarm, seeds, budget and scorer:
  marker  : the normal BlackBoxRobot (perfect marker plus 2 mm noise)
  color   : CameraRobot, red marker, detector 1 (colour segmentation), two views triangulated
  gemini  : CameraRobot, markerless, detector 2 (Gemini Robotics ER), two views triangulated
Structure found and reach error are scored on the TRUE tip, as always (scorer only). A camera reading whose two
views disagree (rays > 20 mm apart) or that misses the tip is a bad observation: CameraRobot returns NaN, the
board files it as `bad_observation` (kept in the provenance, never trained on), and the Monitor never counts it
as a body change (a NaN surprise is never above its threshold). Also renders results/vision_demo.mp4 from the
gemini scara run: both views, the detected points, and the agents' narration as captions.
"""
import argparse
import json
import os
import sys
import time

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402

from bodyscout.blackboard import Blackboard  # noqa: E402
from bodyscout.planning import reach_errors  # noqa: E402
from bodyscout.swarm import make_swarm  # noqa: E402
from bodyscout.world import FAMILIES, BlackBoxRobot, random_body, reachable_targets  # noqa: E402

CONDS = ("marker", "color", "gemini")
NAMES = {"marker": "marker (no camera)", "color": "two cameras, red marker", "gemini": "two cameras, no marker (Gemini)"}
R = "results"


class CameraBlackboard(Blackboard):
    """A camera can fail to see the tip. A non finite reading is filed as a `bad_observation` artifact (same
    payload and parents, so the provenance stays complete) instead of an `observation`, so no modeler trains on
    it and no validator scores on it."""

    def post(self, kind, author, payload, parents=None):
        if kind == "observation" and "x" in payload and not np.all(np.isfinite(payload["x"])):
            kind = "bad_observation"
        return super().post(kind, author, payload, parents)


def narrate(a) -> str | None:
    """One caption line per interesting artifact (what demo.py would print)."""
    p = a.payload
    if a.kind == "finding":
        if p.get("type") == "?":
            return f"{a.author}: channel {p['channel']} barely moves the tip"
        verb = "slides along" if p["type"] == "s" else "rotates about"
        return f"{a.author}: channel {p['channel']} {verb} {p['axis']}"
    if a.kind == "hypothesis":
        return f"{a.author}: proposes {' '.join(p['pattern'])}"
    if a.kind == "champion":
        return f"validators crown the {p['family']} model, holdout {p['holdout_mm']:.1f} mm"
    if a.kind == "bad_observation":
        return f"{a.author}: camera reading rejected (views disagree or tip hidden)"
    if a.kind == "anomaly":
        return "monitor: my body changed!"
    return None


def job(args):
    fam, seed, cond, budget, max_ticks, record = args
    t0 = time.time()
    from bodyscout import vision  # in the worker: each process gets its own EGL context
    robot = BlackBoxRobot(random_body(seed, fam), seed=seed)
    targets = reachable_targets(robot, 8, seed)  # scorer only, costs no motions
    cache = vision.VisionCache("runs/vision")
    pointer = None
    if cond == "marker":
        sensor = robot
    elif cond == "color":
        sensor = vision.CameraRobot(robot, detector="color", cache=cache)
    else:
        pointer = vision.GeminiPointer(max_calls=600)
        sensor = vision.CameraRobot(robot, detector="gemini", markerless=True, cache=cache, pointer=pointer)
    frames = []
    if record and cond != "marker":
        move = sensor.move

        def recorded_move(q):
            x = move(q)
            frames.append({"motion": robot.motions, "images": dict(sensor.last["images"]),
                           "uv": {n: d.get("uv") for n, d in sensor.last["detections"].items()},
                           "bad": sensor.last.get("bad")})
            return x
        sensor.move = recorded_move
    agents = make_swarm(sensor, seed, use_llm=False, channels=True)
    bb, rng = CameraBlackboard(), np.random.default_rng(seed)
    captions, seen = [], 0
    for t in range(max_ticks):
        for i in rng.permutation(len(agents)):
            agents[i].step(bb, t)
        for a in bb.artifacts[seen:]:
            line = narrate(a)
            if line:
                captions.append({"motion": robot.motions, "text": line})
        seen = len(bb.artifacts)
        if robot.motions >= budget:
            break
    champ = bb.latest("champion")
    model = champ.payload["_model"] if champ else None
    reach = float(np.median(reach_errors(robot, model, targets, robot.n_channels, seed))) * 1000 if model else None
    found = (champ.payload.get("describe") or {}).get("structure") if champ else None
    row = {"family": fam, "seed": seed, "condition": cond, "motions": robot.motions, "ticks": t + 1,
           "structure_truth": robot.spec.tokens(), "structure_found": found,
           "structure_correct": found == robot.spec.tokens(), "reach_mm": reach,
           "champion_family": champ.payload["family"] if champ else None,
           "observations": len(bb.of("observation", epoch=-1)), "bad_observations": len(bb.of("bad_observation", epoch=-1)),
           "alarms": len(bb.of("anomaly", epoch=-1)), "gemini_calls": pointer.calls if pointer else 0,
           "gemini_errors": pointer.errors if pointer else 0, "seconds": round(time.time() - t0, 1)}
    if cond != "marker":
        sensor.close()
    return row, {"frames": frames, "captions": captions} if record else None


# ---- figure, summary, video --------------------------------------------------------------------
INK, QUIET, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
COL = {"marker": "#2a78d6", "color": "#eb6834", "gemini": "#1baf7a"}  # validated (dataviz), fixed order


def make_figure(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4.4))
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=QUIET, labelsize=9)
    ax.grid(True, axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    width = 0.26
    fams = [f for f in FAMILIES if any(r["family"] == f for r in rows)]
    for j, cond in enumerate(CONDS):
        for i, fam in enumerate(fams):
            rs = [r for r in rows if r["family"] == fam and r["condition"] == cond]
            ys = [r["reach_mm"] for r in rs if r["reach_mm"] is not None]
            x = i + (j - 1) * width
            if ys:
                med = float(np.median(ys))
                ax.scatter([x] * len(ys), ys, s=22, color=COL[cond], alpha=0.45, edgecolor="none", zorder=2)
                ax.scatter([x], [med], s=70, color=COL[cond], edgecolor=SURF, lw=2, zorder=3,
                           label=NAMES[cond] if i == 0 else None)
                ok = sum(r["structure_correct"] for r in rs)
                ax.annotate(f"{med:.1f}\n{ok}/{len(rs)}", (x, med), textcoords="offset points", xytext=(0, 9),
                            ha="center", fontsize=7.5, color=QUIET)
    ax.set_yscale("log")
    tops = [r["reach_mm"] for r in rows if r["reach_mm"]]
    ax.set_ylim(top=max(tops) * 4 if tops else None)
    ax.set_xticks(range(len(fams)), fams)
    ax.set_ylabel("median reach error on unseen targets, mm (log)", color=QUIET, fontsize=9)
    ax.set_title("Unknown body from cameras vs a marker (labels: median mm, structure found)",
                 color=INK, fontsize=10, loc="left")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3)
    fig.tight_layout()
    fig.savefig(f"{R}/fig_vision.png", dpi=180, facecolor=SURF)


def summary_section(rows, budget, seeds):
    f = lambda v, nd=1: "n/a" if v is None else f"{v:.{nd}f}"  # noqa: E731
    L = ["## Swarm learns from cameras (V3)", "",
         f"Unknown body mode, {seeds} seeds per family, budget {budget} motions, same swarm and scorer in every "
         "condition; reach error and structure are scored on the true tip. Camera readings whose views disagree "
         "(rays > 20 mm apart) or that miss the tip are rejected as bad observations, never as body changes.", "",
         "| family | condition | structure found | median reach error, mm | bad observations (of motions) | Monitor alarms |",
         "| --- | --- | --- | --- | --- | --- |"]
    worse = []
    for fam in [f for f in FAMILIES if any(r["family"] == f for r in rows)]:
        base = [r for r in rows if r["family"] == fam and r["condition"] == "marker"]
        b_ok = sum(r["structure_correct"] for r in base)
        b_ys = [r["reach_mm"] for r in base if r["reach_mm"] is not None]
        b_med = float(np.median(b_ys)) if b_ys else None
        for cond in [c for c in CONDS if any(r["condition"] == c for r in rows)]:
            rs = [r for r in rows if r["family"] == fam and r["condition"] == cond]
            ok = sum(r["structure_correct"] for r in rs)
            ys = [r["reach_mm"] for r in rs if r["reach_mm"] is not None]
            med = float(np.median(ys)) if ys else None
            bad = sum(r["bad_observations"] for r in rs)
            mot = sum(r["motions"] for r in rs)
            L.append(f"| {fam} | {NAMES[cond]} | {ok}/{len(rs)} | {f(med)} | {bad} of {mot} | {sum(r['alarms'] for r in rs)} |")
            if cond != "marker":
                if ok < b_ok:
                    worse.append(f"{fam}, {NAMES[cond]}: structure found {ok}/{len(rs)} vs {b_ok}/{len(base)} with the marker")
                if med is None and b_med is not None:
                    worse.append(f"{fam}, {NAMES[cond]}: no model by the end of the budget (marker: {f(b_med)} mm)")
                elif med is not None and b_med is not None and med > 1.25 * b_med and med - b_med > 1.0:
                    worse.append(f"{fam}, {NAMES[cond]}: median reach error {f(med)} mm vs {f(b_med)} mm with the marker")
    L += ["", "### Where camera input makes things worse", ""]
    L += [f"- {w}" for w in worse] if worse else ["- Nowhere at this sample size (within 25% or 1 mm of the marker)."]
    L += ["", "Notes: a camera reading that is rejected still costs its motion. A rejected reading resets the stock "
          "Monitor's strike count (its NaN surprise is never above threshold), which can delay a real alarm by one "
          "sentinel. LLM hypothesizers are off in every condition so the only model in the loop is the detector.", ""]
    return L


def make_video(rec, path, seconds=20, fps=10):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    frames, caps = rec["frames"], rec["captions"]
    if not frames:
        return False
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        font = small = ImageFont.load_default()
    n_out = seconds * fps
    writer = imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=8)
    for k in range(n_out):
        fr = frames[min(len(frames) - 1, int(k * len(frames) / n_out))]
        canvas = Image.new("RGB", (1280, 600), (252, 252, 251))
        for i, name in enumerate(("front", "side")):
            img = Image.open(f"runs/vision/images/{fr['images'][name]}.png").convert("RGB")
            d = ImageDraw.Draw(img)
            uv = fr["uv"].get(name)
            if uv is not None:
                u, v = uv
                d.ellipse([u - 9, v - 9, u + 9, v + 9], outline=(27, 175, 122), width=3)
                d.line([u - 14, v, u + 14, v], fill=(27, 175, 122), width=2)
                d.line([u, v - 14, u, v + 14], fill=(27, 175, 122), width=2)
            d.text((10, 8), f"{name} camera", fill=(240, 240, 240), font=small)
            canvas.paste(img, (i * 640, 0))
        d = ImageDraw.Draw(canvas)
        lines = [c["text"] for c in caps if c["motion"] <= fr["motion"]][-2:]
        status = f"motion {fr['motion']}  |  Gemini Robotics ER points at the tip in each view (green), triangulated"
        if fr.get("bad"):
            status += f"  |  rejected: {fr['bad']}"
        d.text((14, 492), status, fill=(82, 81, 78), font=small)
        for j, line in enumerate(lines):
            d.text((14, 522 + 30 * j), line, fill=(11, 11, 11), font=font)
        writer.append_data(np.asarray(canvas))
    writer.close()
    return True


if __name__ == "__main__":
    import multiprocessing as mp
    import re

    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--budget", type=int, default=64)
    ap.add_argument("--max-ticks", type=int, default=400)
    ap.add_argument("--procs", type=int, default=12)
    ap.add_argument("--video-family", default="scara")
    ap.add_argument("--families", nargs="+", default=list(FAMILIES))
    ap.add_argument("--conds", nargs="+", default=list(CONDS))
    ap.add_argument("--out", default=R, help="where the json, figure, summary and video go")
    ap.add_argument("--video-seconds", type=int, default=20)
    ap.add_argument("--plot", action="store_true", help="figure and summary from the saved json, no runs")
    ap.add_argument("--video-only", action="store_true", help="replay only the video run (Gemini answers cached)")
    a = ap.parse_args()
    R = a.out
    if a.plot or a.video_only:
        saved = json.load(open(f"{R}/vision_swarm.json"))
        rows = saved["rows"]
        if a.video_only:
            rec_path = "runs/vision/video_run.json"
            if os.path.exists(rec_path):
                rec = json.load(open(rec_path))
            else:
                _, rec = job((a.video_family, 1, "gemini", saved["args"]["budget"], saved["args"]["max_ticks"], True))
                json.dump(rec, open(rec_path, "w"))
            print("video:", make_video(rec, f"{R}/vision_demo.mp4", seconds=a.video_seconds))
        make_figure(rows)
        sys.exit(0)
    t0 = time.time()
    jobs = [(fam, s, c, a.budget, a.max_ticks, fam == a.video_family and s == 1 and c == "gemini")
            for fam in a.families for s in range(1, a.seeds + 1) for c in a.conds]
    with mp.get_context("spawn").Pool(a.procs) as pool:
        out = pool.map(job, jobs)
    rows = [r for r, _ in out]
    rec = next((x for _, x in out if x), None)
    os.makedirs(R, exist_ok=True)
    if rec:
        json.dump(rec, open("runs/vision/video_run.json", "w"))
    json.dump({"args": vars(a), "rows": rows}, open(f"{R}/vision_swarm.json", "w"), indent=1, default=str)
    make_figure(rows)
    path = f"{R}/summary_vision.md"
    old = open(path).read() if os.path.exists(path) else "# Vision: two cameras instead of a marker\n"
    old = re.split(r"\n## Swarm learns from cameras .*", old, maxsplit=1, flags=re.S)[0].rstrip() + "\n\n"
    open(path, "w").write(old + "\n".join(summary_section(rows, a.budget, a.seeds)))
    ok = make_video(rec, f"{R}/vision_demo.mp4", seconds=a.video_seconds) if rec else False
    print("\n".join(summary_section(rows, a.budget, a.seeds)))
    print(f"video: {R + '/vision_demo.mp4' if ok else 'not made'}; total {time.time() - t0:.0f}s; "
          f"gemini calls {sum(r['gemini_calls'] for r in rows)}")
