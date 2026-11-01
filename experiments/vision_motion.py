"""Active perception: the end of the chain is the only part that moves whichever joint moves. Run on the GPU box:

    MUJOCO_GL=egl python experiments/vision_motion.py [--cameras 2|4]

For each of the same 200 poses per family (as the other vision benchmarks), render the pose, then the pose with
each channel nudged in turn. In every view, the robot pixels that change when channel k moves belong to the links
after joint k; intersecting over all channels leaves the last link. Its far end (farthest from the rest of the
robot) is snapped to the end cap and triangulated. No Gemini, no robot geometry: it needs n_channels + 1 renders
per reading, which on a real robot would be extra motions, so it is a calibration tool rather than a per reading
sensor. Truth is the rendered tip (scoring only). Writes results/vision_motion.json.
"""
import argparse
import json
import os
import sys
import time

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

import vision_improve as VI  # noqa: E402
from bodyscout import vision  # noqa: E402
from bodyscout.world import FAMILIES, SLIDE_GAIN, BlackBoxRobot, random_body  # noqa: E402

NUDGE = 0.3  # command units: 0.3 rad on a hinge, 0.3 x 6 cm on a slide


def robot_mask(img):
    rgb = img.astype(np.int32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (b > 50) & (b > r + 25) & (b > g + 5)


def last_link_end(base_img, nudged_imgs):
    """The tip from motion alone: the robot pixels that change under EVERY channel's nudge are the last link.
    Tiny region (a last joint that barely moves its link): its centre is the tip. Otherwise pick the end of the
    region nearer the centre of what the most distal channel's nudge swept (the channel moving the fewest robot
    pixels): points farther from that joint sweep further, so the sweep concentrates toward the tip. Snapped to
    the end cap. Returns pixel coordinates or None."""
    rob = robot_mask(base_img)
    if rob.sum() < 20:
        return None
    base = base_img.astype(np.int32)
    changed = [np.abs(img.astype(np.int32) - base).sum(-1) > 30 for img in nudged_imgs]
    moved_all = rob.copy()
    for c in changed:
        moved_all &= c
    n = int(moved_all.sum())
    if n == 0:
        return None
    vs, us = np.nonzero(moved_all)
    P = np.stack([us + 0.5, vs + 0.5], 1)
    if n < 15:
        return vision.refine_tip(base_img, P.mean(0))["uv"]
    distal = int(np.argmin([(rob & c).sum() for c in changed]))
    sv, su = np.nonzero(changed[distal])
    sweep = np.array([su.mean() + 0.5, sv.mean() + 0.5])
    mu = P.mean(0)
    evals, evecs = np.linalg.eigh(np.cov((P - mu).T))
    d = evecs[:, 1]
    proj = (P - mu) @ d
    ends = [P[np.argmin(proj)], P[np.argmax(proj)]]
    tip = min(ends, key=lambda e: np.linalg.norm(e - sweep))
    return vision.refine_tip(base_img, tip)["uv"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cameras", type=int, default=2, choices=[2, 4])
    a = ap.parse_args()
    cams_cfg, (W, H) = (vision.CAMERAS, (640, 480)) if a.cameras == 2 else (vision.CAMERAS4, (1280, 960))
    t0 = time.time()
    poses, located = [], []
    for fam in FAMILIES:
        for seed in range(1, 6):
            robot = BlackBoxRobot(random_body(seed, fam), seed=seed)
            cam = vision.CameraRobot(robot, detector="gemini", markerless=True, pointer=False, cameras=cams_cfg,
                                     width=W, height=H, max_gap_mm=None,
                                     cache=vision.VisionCache("runs/vision_motion", save_images=False))
            rng = np.random.default_rng(1000 + seed)
            slide = np.array([t == "s" for t in robot.spec.types])  # only to convert the nudge to joint units
            for _ in range(40):
                robot.move(rng.uniform(*robot.limits, robot.n_channels))
                views = cam.render_views()
                truth = cam.true_tip()
                q0 = cam.data.qpos.copy()
                nudged = []
                for k in range(robot.n_channels):  # render the pose with channel k nudged (what a wiggle shows)
                    q = q0.copy()
                    q[k] += NUDGE * (SLIDE_GAIN if slide[k] else 1.0) * (1 if q[k] < 0 else -1)
                    cam.data.qpos[:] = q
                    mujoco.mj_forward(cam.model, cam.data)
                    imgs = []
                    for name in cam.cameras:
                        cam._renderer.update_scene(cam.data, camera=name)
                        imgs.append(cam._renderer.render().copy())
                    nudged.append(imgs)
                cam.data.qpos[:] = q0
                mujoco.mj_forward(cam.model, cam.data)
                uvs = [last_link_end(img, [nudged[k][v] for k in range(robot.n_channels)])
                       for v, (_, img, _) in enumerate(views)]
                poses.append({"family": fam, "truth": truth})
                if all(u is not None for u in uvs):
                    X, g, _ = vision.triangulate_n([c for _, _, c in views], uvs, 1e9)
                    located.append((X, g))
                else:
                    located.append((None, None))
            cam.close()
        print(f"{fam}: {time.time() - t0:.0f}s", flush=True)
    res = VI.score(poses, located)
    for fam, s in res.items():
        print(f"{fam:10s} accepted {s['accepted']:3d}/200  median {s['median_mm'] if s['median_mm'] is None else round(s['median_mm'], 1)}"
              f"  p90 {s['p90_mm'] if s['p90_mm'] is None else round(s['p90_mm'], 1)} mm")
    path = "results/vision_motion.json"
    saved = json.load(open(path)) if os.path.exists(path) else {}
    saved[f"{a.cameras} cameras"] = res
    json.dump(saved, open(path, "w"), indent=1)
