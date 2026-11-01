"""V1: how well do two cameras + the red marker detector locate the tip? Run on the Brev GPU instance:

    MUJOCO_GL=egl python experiments/vision_accuracy.py            # 200 poses per family -> results/

For each family, 5 bodies x 40 random poses. Truth is the tip MuJoCo rendered (scoring only). A pose is
"out of view" if the true tip projects outside either image, "hidden" if it is in view but the detector finds
no red in at least one view (covered by a link). Error = distance between triangulated and true tip.
"""
import argparse
import json
import os
import sys
import time

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402

from bodyscout import vision  # noqa: E402
from bodyscout.world import FAMILIES, BlackBoxRobot, random_body  # noqa: E402


def run_family(fam, n_poses, n_bodies, cache):
    rows = []
    per_body = n_poses // n_bodies
    for seed in range(1, n_bodies + 1):
        robot = BlackBoxRobot(random_body(seed, fam), seed=seed)
        cam = vision.CameraRobot(robot, cache=cache, max_gap_mm=None)
        rng = np.random.default_rng(1000 + seed)
        for _ in range(per_body):
            q = rng.uniform(*cam.limits, cam.n_channels)
            est = cam.move(q)
            truth = cam.true_tip()
            mats = [vision.camera_matrices(cam.model, cam.data, n) for n in cam.cameras]
            uv_true = [vision.project(m, truth)[0] for m in mats]
            in_view = all(np.all(np.isfinite(u)) and 0 <= u[0] <= cam.width and 0 <= u[1] <= cam.height
                          for u in uv_true)
            dets = list(cam.last["detections"].values())
            found = all(d["found"] for d in dets)
            px = [float(np.linalg.norm(np.array(d["uv"]) - u)) if d["found"] else None for d, u in zip(dets, uv_true)]
            rows.append({"family": fam, "seed": seed, "in_view": bool(in_view), "found": bool(found),
                         "err_mm": float(np.linalg.norm(est - truth) * 1000) if found else None,
                         "residual_mm": cam.last["residual_m"] * 1000 if found else None,
                         "px_err": px, "pixels": [d["pixels"] for d in dets]})
        cam.close()
    return rows


def summarize(rows):
    out = {}
    for fam in sorted({r["family"] for r in rows}, key=list(FAMILIES).index):
        rs = [r for r in rows if r["family"] == fam]
        err = np.array([r["err_mm"] for r in rs if r["found"]])
        px = np.array([p for r in rs if r["found"] for p in r["px_err"]])
        res = np.array([r["residual_mm"] for r in rs if r["found"]])
        out[fam] = {"n": len(rs), "detected": int(len(err)),
                    "out_of_view": sum(not r["in_view"] for r in rs),
                    "hidden": sum(r["in_view"] and not r["found"] for r in rs),
                    "found_but_out_of_view": sum((not r["in_view"]) and r["found"] for r in rs),
                    "median_mm": float(np.median(err)) if len(err) else None,
                    "p90_mm": float(np.percentile(err, 90)) if len(err) else None,
                    "max_mm": float(err.max()) if len(err) else None,
                    "median_px": float(np.median(px)) if len(px) else None,
                    "median_residual_mm": float(np.median(res)) if len(res) else None}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", type=int, default=200)
    ap.add_argument("--bodies", type=int, default=5)
    a = ap.parse_args()
    t0 = time.time()
    cache = vision.VisionCache("runs/vision")
    rows = []
    for fam in FAMILIES:
        rows += run_family(fam, a.poses, a.bodies, cache)
        print(f"{fam}: done ({time.time() - t0:.0f}s)", flush=True)
    summ = summarize(rows)
    os.makedirs("results", exist_ok=True)
    gl = {}
    probe = vision.CameraRobot(BlackBoxRobot(random_body(1, "arm")), cache=cache)
    probe.observe()
    gl = probe.gl
    probe.close()
    json.dump({"args": vars(a), "cameras": vision.CAMERAS, "gl": gl, "summary": summ, "rows": rows},
              open("results/vision_accuracy.json", "w"), indent=1)
    L = ["# Vision: two cameras instead of a marker", "",
         "## Detector 1: red tip sphere, two fixed cameras (V1)", "",
         f"Two fixed cameras ({', '.join(f'{k} at {v['pos']} m, fovy {v['fovy']} deg' for k, v in vision.CAMERAS.items())}), "
         f"{vision.WIDTH}x{vision.HEIGHT}, rendered with EGL on {gl.get('gl_renderer', '?')}. Camera matrices come from "
         "the MuJoCo camera parameters only. Per family: "
         f"{a.bodies} bodies x {a.poses // a.bodies} random poses. Error is the distance between the triangulated "
         "and the true rendered tip.", "",
         "| family | poses | detected in both views | hidden (in view, covered) | out of view | median error, mm | 90th percentile, mm | median pixel error | median ray gap, mm |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    f = lambda v, nd=1: "n/a" if v is None else f"{v:.{nd}f}"  # noqa: E731
    for fam, s in summ.items():
        L.append(f"| {fam} | {s['n']} | {s['detected']} ({100 * s['detected'] / s['n']:.0f}%) | "
                 f"{s['hidden']} ({100 * s['hidden'] / s['n']:.0f}%) | {s['out_of_view']} ({100 * s['out_of_view'] / s['n']:.0f}%) | "
                 f"{f(s['median_mm'])} | {f(s['p90_mm'])} | {f(s['median_px'], 2)} | {f(s['median_residual_mm'])} |")
    L += ["", "Hidden and out of view poses return NaN instead of a guess. For comparison, the marker robot's "
          "simulated camera noise is 2 mm per axis (about 3.5 mm as a 3D distance).", "",
          "Detector note: the colour rule was changed once before this run, after a check on 110 views of other "
          "poses showed brightness weighting biased the centroid about 0.9 px upward (overhead light shades the "
          "lower half of the sphere).", ""]
    open("results/summary_vision.md", "w").write("\n".join(L))
    print("\n".join(L))
    print(f"total {time.time() - t0:.0f}s")
