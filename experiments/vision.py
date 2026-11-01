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

from bodyscout.planning import reach_errors  # noqa: E402
from bodyscout.swarm import make_swarm  # noqa: E402
from bodyscout.world import FAMILIES, BlackBoxRobot, random_body, reachable_targets  # noqa: E402

CONDS = ("marker", "color", "gemini", "gemini_plus_drop", "gemini_plus")
NAMES = {"marker": "marker (no camera)", "color": "two cameras, red marker", "gemini": "two cameras, no marker (Gemini)",
         "gemini_plus_drop": "4 cameras, no marker, improved, drop 1 view",
         "gemini_plus": "4 cameras, no marker, improved, all views agree"}
PLUS = {"pipeline": "refine", "cameras": 4, "width": 1280, "height": 960}  # the improved detector (V5)
R = "results"


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
    fam, seed, cond, budget, max_ticks, record, plus = args
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
        pointer = vision.GeminiPointer(max_calls=600 if cond == "gemini" else 2400,
                                       max_calls_per_min=50)  # 8 parallel runs x 50 = the 400/min spend rule
        kw = {} if cond == "gemini" else {"pipeline": plus["pipeline"], "width": plus["width"], "height": plus["height"],
                                          "cameras": vision.CAMERAS4 if plus["cameras"] == 4 else vision.CAMERAS,
                                          "drop_views": cond == "gemini_plus_drop"}
        sensor = vision.CameraRobot(robot, detector="gemini", markerless=True, cache=cache, pointer=pointer, **kw)
    frames = []
    if record and cond != "marker":
        move = sensor.move

        def recorded_move(q):
            x = move(q)
            truth = sensor.true_tip()  # scorer only: drawn in the video so the error is visible
            cams = {n: vision.camera_matrices(sensor.model, sensor.data, n, sensor.width, sensor.height)
                    for n in sensor.cameras}
            frames.append({"motion": robot.motions, "images": dict(sensor.last["images"]),
                           "uv": {n: (d.get("used_uv") or d.get("uv")) for n, d in sensor.last["detections"].items()},
                           "truth_uv": {n: vision.project(c, truth)[0].tolist() for n, c in cams.items()},
                           "bad": sensor.last.get("bad"), "size": [sensor.width, sensor.height],
                           "err_mm": None if np.isnan(x).any() else float(np.linalg.norm(x - truth) * 1000)})
            return x
        sensor.move = recorded_move
    agents = make_swarm(sensor, seed, use_llm=False, channels=True)
    bb, rng = vision.CameraBlackboard(), np.random.default_rng(seed)
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
           "gemini_errors": pointer.errors if pointer else 0, "seconds": round(time.time() - t0, 1),
           "setup": None if cond in ("marker", "color", "gemini") else {**plus, "drop_views": cond == "gemini_plus_drop"}}
    if cond != "marker":
        sensor.close()
    return row, {"cond": cond, "frames": frames, "captions": captions} if record else None


# ---- figure, summary, video --------------------------------------------------------------------
INK, QUIET, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
COL = {"marker": "#2a78d6", "color": "#eb6834", "gemini": "#1baf7a", "gemini_plus_drop": "#eda100",
       "gemini_plus": "#e87ba4"}  # validated (dataviz), fixed order


def make_figure(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12.5, 5.2))
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=QUIET, labelsize=9)
    ax.grid(True, axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    width = 0.16
    fams = [f for f in FAMILIES if any(r["family"] == f for r in rows)]
    conds = [c for c in CONDS if any(r["condition"] == c for r in rows)]
    for j, cond in enumerate(conds):
        for i, fam in enumerate(fams):
            rs = [r for r in rows if r["family"] == fam and r["condition"] == cond]
            ys = [r["reach_mm"] for r in rs if r["reach_mm"] is not None]
            x = i + (j - (len(conds) - 1) / 2) * width
            if ys:
                med = float(np.median(ys))
                ax.scatter([x] * len(ys), ys, s=22, color=COL[cond], alpha=0.45, edgecolor="none", zorder=2)
                ax.scatter([x], [med], s=70, color=COL[cond], edgecolor=SURF, lw=2, zorder=3,
                           label=NAMES[cond] if i == 0 else None)
                ok = sum(r["structure_correct"] for r in rs)
                above = j % 2 == 0  # alternate above / below so neighbouring labels do not collide
                ax.annotate(f"{med:.1f}\n{ok}/{len(rs)}", (x, med), textcoords="offset points",
                            xytext=(0, 8 if above else -10), va="bottom" if above else "top",
                            ha="center", fontsize=7, color=QUIET)
    ax.set_yscale("log")
    tops = [r["reach_mm"] for r in rows if r["reach_mm"]]
    ax.set_ylim(bottom=min(tops) / 3 if tops else None, top=max(tops) * 4 if tops else None)
    ax.set_xticks(range(len(fams)), fams)
    ax.set_ylabel("median reach error on unseen targets, mm (log)", color=QUIET, fontsize=9)
    ax.set_title("Unknown body from cameras vs a marker (labels: median mm, structure found)",
                 color=INK, fontsize=10, loc="left")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3)
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


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _view(fr, name, size):
    """One camera view at `size`, with the detected point (green cross) and the true tip (yellow ring,
    scorer only)."""
    from PIL import Image, ImageDraw
    img = Image.open(f"runs/vision/images/{fr['images'][name]}.png").convert("RGB")
    sx, sy = size[0] / img.width, size[1] / img.height
    img = img.resize(size)
    d = ImageDraw.Draw(img)
    t = (fr.get("truth_uv") or {}).get(name)
    if t is not None and np.all(np.isfinite(t)):
        u, v = t[0] * sx, t[1] * sy
        d.ellipse([u - 11, v - 11, u + 11, v + 11], outline=(240, 200, 40), width=2)
    uv = fr["uv"].get(name)
    if uv is not None:
        u, v = uv[0] * sx, uv[1] * sy
        d.line([u - 12, v, u + 12, v], fill=(27, 175, 122), width=3)
        d.line([u, v - 12, u, v + 12], fill=(27, 175, 122), width=3)
    d.text((8, 6), f"{name} camera", fill=(240, 240, 240), font=_font(15))
    return img


def make_video(rec, path, title, seconds=20, fps=10):
    """Every camera view of one run (2 side by side, or a 2 x 2 grid), narration as captions."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw

    frames, caps = rec["frames"], rec["captions"]
    if not frames:
        return False
    names = list(frames[0]["images"])
    grid = (2, 1) if len(names) <= 2 else (2, 2)
    cell = (640, 480)
    W, H = cell[0] * grid[0], cell[1] * grid[1] + 140
    writer = imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=8)
    for k in range(seconds * fps):
        fr = frames[min(len(frames) - 1, int(k * len(frames) / (seconds * fps)))]
        canvas = Image.new("RGB", (W, H), (252, 252, 251))
        for i, name in enumerate(names):
            canvas.paste(_view(fr, name, cell), ((i % grid[0]) * cell[0], (i // grid[0]) * cell[1]))
        d = ImageDraw.Draw(canvas)
        y0 = cell[1] * grid[1]
        err = "rejected: " + fr["bad"] if fr.get("bad") else (f"error {fr['err_mm']:.1f} mm" if fr.get("err_mm") is not None else "")
        d.text((14, y0 + 8), f"{title}  |  motion {fr['motion']}  |  {err}", fill=(11, 11, 11), font=_font(17))
        d.text((14, y0 + 34), "green cross = where the detector says the tip is;  yellow ring = true tip (scorer only)",
               fill=(82, 81, 78), font=_font(14))
        for j, line in enumerate([c["text"] for c in caps if c["motion"] <= fr["motion"]][-2:]):
            d.text((14, y0 + 62 + 30 * j), line, fill=(11, 11, 11), font=_font(18))
        writer.append_data(np.asarray(canvas))
    writer.close()
    return True


def make_compare_video(recs, path, seconds=20, fps=10):
    """The front camera of each condition side by side, same body and seed, so the difference is visible."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw

    conds = [c for c in ("color", "gemini", "gemini_plus") if c in recs and recs[c]["frames"]]  # marker, before, after
    if len(conds) < 2:
        return False
    cell = (640, 480)
    W, H = cell[0] * len(conds), cell[1] + 120
    writer = imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=8)
    for k in range(seconds * fps):
        canvas = Image.new("RGB", (W, H), (252, 252, 251))
        d = ImageDraw.Draw(canvas)
        for i, c in enumerate(conds):
            fr = recs[c]["frames"][min(len(recs[c]["frames"]) - 1, int(k * len(recs[c]["frames"]) / (seconds * fps)))]
            canvas.paste(_view(fr, "front", cell), (i * cell[0], 0))
            err = "rejected" if fr.get("bad") else (f"{fr['err_mm']:.1f} mm off" if fr.get("err_mm") is not None else "")
            d.text((i * cell[0] + 14, cell[1] + 10), NAMES[c], fill=(11, 11, 11), font=_font(19))
            d.text((i * cell[0] + 14, cell[1] + 40), f"motion {fr['motion']}  |  this reading: {err}", fill=(82, 81, 78), font=_font(16))
        d.text((14, cell[1] + 80), "front camera of each run, same SCARA and seed.  green cross = detected tip;  yellow ring = true tip (scorer only)",
               fill=(82, 81, 78), font=_font(15))
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
    ap.add_argument("--conds", nargs="+", default=list(CONDS), help="rerun these; rows of other conditions are kept")
    ap.add_argument("--plus-pipeline", default=PLUS["pipeline"], choices=["point", "refine", "zoom", "multi"])
    ap.add_argument("--plus-cameras", type=int, default=PLUS["cameras"], choices=[2, 4])
    ap.add_argument("--plus-res", default=f"{PLUS['width']}x{PLUS['height']}")
    ap.add_argument("--out", default=R)
    ap.add_argument("--video-seconds", type=int, default=20)
    ap.add_argument("--plot", action="store_true", help="figure, summary and videos from saved results, no runs")
    a = ap.parse_args()
    R = a.out
    w, h = (int(x) for x in a.plus_res.split("x"))
    plus = {"pipeline": a.plus_pipeline, "cameras": a.plus_cameras, "width": w, "height": h}
    t0 = time.time()
    path_json = f"{R}/vision_swarm.json"
    saved = json.load(open(path_json)) if os.path.exists(path_json) else {"rows": []}
    rows = saved["rows"]
    if not a.plot:
        jobs = [(fam, s, c, a.budget, a.max_ticks, fam == a.video_family and s == 1 and c != "marker", plus)
                for fam in a.families for s in range(1, a.seeds + 1) for c in a.conds]
        with mp.get_context("spawn").Pool(a.procs) as pool:
            out = pool.map(job, jobs)
        new = [r for r, _ in out]
        redone = {(r["family"], r["seed"], r["condition"]) for r in new}
        rows = [r for r in rows if (r["family"], r["seed"], r["condition"]) not in redone] + new
        for _, rec in out:
            if rec:
                json.dump(rec, open(f"runs/vision/video_{rec['cond']}.json", "w"))
        os.makedirs(R, exist_ok=True)
        json.dump({"args": vars(a), "plus": plus, "rows": rows}, open(path_json, "w"), indent=1, default=str)
    rows.sort(key=lambda r: (list(FAMILIES).index(r["family"]), r["seed"], CONDS.index(r["condition"])))
    make_figure(rows)
    path = f"{R}/summary_vision.md"
    old = open(path).read() if os.path.exists(path) else "# Vision: two cameras instead of a marker\n"
    old = re.split(r"\n## Swarm learns from cameras .*", old, maxsplit=1, flags=re.S)[0].rstrip() + "\n\n"
    open(path, "w").write(old + "\n".join(summary_section(rows, a.budget, a.seeds)))
    recs = {}
    for c in ("color", "gemini", "gemini_plus_drop", "gemini_plus"):
        f = f"runs/vision/video_{c}.json"
        if os.path.exists(f):
            recs[c] = json.load(open(f))
    titles = {"color": "two cameras, red marker", "gemini": "no marker: Gemini points once, 2 cameras",
              "gemini_plus_drop": "no marker: improved Gemini, 4 cameras, drop 1 view",
              "gemini_plus": "no marker: improved Gemini, 4 cameras, all views agree"}
    for c, rec in recs.items():
        name = {"color": "vision_demo_marker", "gemini": "vision_demo_gemini", "gemini_plus_drop": "vision_demo_gemini_plus_drop",
                "gemini_plus": "vision_demo_gemini_plus"}[c]
        make_video(rec, f"{R}/{name}.mp4", titles[c], seconds=a.video_seconds)
    make_compare_video(recs, f"{R}/vision_compare.mp4", seconds=a.video_seconds)
    print("\n".join(summary_section(rows, a.budget, a.seeds)))
    print(f"videos: {sorted(recs)}; total {time.time() - t0:.0f}s; gemini calls {sum(r['gemini_calls'] for r in rows)}")
