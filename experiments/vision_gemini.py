"""V2: no marker. Gemini Robotics ER points at the tip in each view; compare with the red marker detector on
the SAME 200 poses per family as experiments/vision_accuracy.py. Run on the Brev GPU instance:

    MUJOCO_GL=egl python experiments/vision_gemini.py [--max-calls 2000] [--workers 16]

Each pose is rendered twice: with the red marker (detector 1, colour) and markerless (tip painted like the
links; detector 2, Gemini). Gemini answers are cached by image hash under runs/vision/, so a rerun is free and
repeatable. Truth is the rendered tip (scoring only).
"""
import argparse
import json
import os
import re
import sys
import time

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402

from bodyscout import vision  # noqa: E402
from bodyscout.world import FAMILIES, BlackBoxRobot, random_body  # noqa: E402

BAD_GAP_MM = 20.0


def collect(fam, n_poses, n_bodies, cache):
    """Same bodies and poses as vision_accuracy.py: seeds 1..n_bodies, rng 1000 + seed."""
    out = []
    for seed in range(1, n_bodies + 1):
        robot = BlackBoxRobot(random_body(seed, fam), seed=seed)
        marker = vision.CameraRobot(robot, detector="color", cache=cache, max_gap_mm=None)
        plain = vision.CameraRobot(robot, detector="gemini", markerless=True, cache=cache, pointer=False,
                                    max_gap_mm=None)
        rng = np.random.default_rng(1000 + seed)
        for _ in range(n_poses // n_bodies):
            robot.move(rng.uniform(*robot.limits, robot.n_channels))
            est_color = marker.observe()
            views = plain.render_views()
            out.append({"family": fam, "seed": seed, "truth": plain.true_tip(), "est_color": est_color,
                        "color_gap": marker.last["residual_m"], "views": views, "plain": plain})
        marker.close()
    return out


def stats(err, gaps=None):
    err = np.asarray([e for e in err if e is not None], float)
    s = {"n": int(len(err)), "median_mm": float(np.median(err)) if len(err) else None,
         "p90_mm": float(np.percentile(err, 90)) if len(err) else None}
    if gaps is not None:
        g = np.asarray([x for x in gaps if x is not None], float)
        s["bad_gap"] = int((g > BAD_GAP_MM).sum())
        s["median_gap_mm"] = float(np.median(g)) if len(g) else None
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", type=int, default=200)
    ap.add_argument("--bodies", type=int, default=5)
    ap.add_argument("--max-calls", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    t0 = time.time()
    cache = vision.VisionCache("runs/vision")
    pointer = vision.GeminiPointer(max_calls=a.max_calls)
    print(f"Gemini model: {pointer.model}", flush=True)
    poses = []
    for fam in FAMILIES:
        poses += collect(fam, a.poses, a.bodies, cache)
        print(f"{fam}: rendered ({time.time() - t0:.0f}s)", flush=True)

    images = [img for p in poses for _, img, _ in p["views"]]
    dets = vision.detect_many(images, pointer, cache, pointer.cache_name, workers=a.workers)
    print(f"Gemini: {len(images)} images, {pointer.calls} real calls (rest cached), {pointer.errors} errors, "
          f"{time.time() - t0:.0f}s", flush=True)

    rows = []
    for i, p in enumerate(poses):
        d2 = dets[2 * i: 2 * i + 2]
        est = p["plain"].locate(p["views"], d2)
        gap = p["plain"].last["residual_m"]
        px = []
        for (_, _, cam), d in zip(p["views"], d2):
            uv_t = vision.project(cam, p["truth"])[0]
            px.append(float(np.linalg.norm(np.array(d["uv"]) - uv_t)) if d["found"] else None)
        ok_c = bool(np.all(np.isfinite(p["est_color"])))
        ok_g = bool(np.all(np.isfinite(est)))
        rows.append({"family": p["family"], "seed": p["seed"],
                     "color_err_mm": float(np.linalg.norm(p["est_color"] - p["truth"]) * 1000) if ok_c else None,
                     "gemini_err_mm": float(np.linalg.norm(est - p["truth"]) * 1000) if ok_g else None,
                     "gemini_gap_mm": gap * 1000 if gap is not None else None,
                     "gemini_px_err": px, "gemini_errors": [d.get("error") for d in d2],
                     "gemini_raw": [d.get("raw") for d in d2]})
    for p in poses:
        p["plain"].close()

    summ = {}
    for fam in FAMILIES:
        rs = [r for r in rows if r["family"] == fam]
        summ[fam] = {"poses": len(rs),
                     "color": stats([r["color_err_mm"] for r in rs]),
                     "gemini": stats([r["gemini_err_mm"] for r in rs], [r["gemini_gap_mm"] for r in rs]),
                     "gemini_no_point": sum(1 for r in rs for e, x in zip(r["gemini_errors"], r["gemini_px_err"])
                                            if x is None and e is None),
                     "gemini_failed_calls": sum(1 for r in rs for e in r["gemini_errors"] if e),
                     "gemini_median_px": float(np.median([x for r in rs for x in r["gemini_px_err"] if x is not None]))}
    json.dump({"args": vars(a), "model": pointer.model, "calls": pointer.calls, "errors": pointer.errors,
               "summary": summ, "rows": rows}, open("results/vision_gemini.json", "w"), indent=1)

    f = lambda v, nd=1: "n/a" if v is None else f"{v:.{nd}f}"  # noqa: E731
    L = ["## Detector 2: no marker, Gemini Robotics ER (V2)", "",
         f"Same 200 poses per family as above. Markerless: the tip sphere is painted like the links. Gemini "
         f"(`{pointer.model}`, temperature 0) is asked to point to the end of the robot's last link in each view; "
         f"its normalized [y, x] point is triangulated as before. {len(images)} images, {pointer.calls} real calls "
         f"this run (answers are cached by image hash, so reruns are free), {pointer.errors} call errors. "
         f"\"Bad disagreement\" = the two views' rays miss each other by more than {BAD_GAP_MM:.0f} mm.", "",
         "| family | poses | colour marker: located | colour: median / p90, mm | Gemini markerless: located | Gemini: median / p90, mm | Gemini views disagree badly (> 20 mm) | Gemini median pixel error |",
         "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for fam, s in summ.items():
        c, g = s["color"], s["gemini"]
        L.append(f"| {fam} | {s['poses']} | {c['n']} ({100 * c['n'] / s['poses']:.0f}%) | {f(c['median_mm'])} / {f(c['p90_mm'])} | "
                 f"{g['n']} ({100 * g['n'] / s['poses']:.0f}%) | {f(g['median_mm'])} / {f(g['p90_mm'])} | "
                 f"{g['bad_gap']} of {g['n']} ({100 * g['bad_gap'] / max(g['n'], 1):.0f}%) | {f(s['gemini_median_px'], 1)} |")
    L += ["", "Located = a point in both views (Gemini: it answered with a point in both; colour: the red sphere was "
          "visible in both). Markerless mode has no fallback; the colour detector is only a fallback in marker "
          "mode.", ""]
    path = "results/summary_vision.md"
    old = open(path).read() if os.path.exists(path) else "# Vision: two cameras instead of a marker\n"
    old = re.split(r"\n## Detector 2: .*", old, maxsplit=1, flags=re.S)[0].rstrip() + "\n\n"
    open(path, "w").write(old + "\n".join(L))
    print("\n".join(L))
    print(f"total {time.time() - t0:.0f}s")
