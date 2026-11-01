"""SCARA, markerless: does knowing the structure, or walking to the chain's end, find the tip? Run on the GPU box:

    MUJOCO_GL=egl python experiments/vision_scara.py

Same 200 SCARA poses as the other vision benchmarks, 4 cameras at 1280x960. Candidates per view:
  S  Gemini asked with the structure-informed question (structure_prompt of the body's tokens), snapped
  F  chain_end: walk the robot's pixels from the mount to the chain's end (no Gemini), snapped
Each is triangulated with one disagreeing view dropped, or strictly (every view must agree); "either" keeps, per
pose, the combination of S / F candidates whose rays agree best. Writes results/vision_scara.json.
"""
import hashlib
import itertools
import json
import os
import sys

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

import vision_improve as VI  # noqa: E402
from bodyscout import vision  # noqa: E402
from bodyscout.world import random_body  # noqa: E402

NV = 4


def tri(poses, k, uvs, strict):
    cams = [c for _, _, c in poses[k]["views"]]
    pts = [(cams[v], u) for v, u in enumerate(uvs) if u is not None]
    if len(pts) < 2 or (strict and len(pts) < NV):
        return (None, None)
    X, g, _ = vision.triangulate_n([c for c, _ in pts], [u for _, u in pts], 1e9 if strict else 0.02)
    return (X, g)


def either(poses, S, F, strict):
    out = []
    for k, p in enumerate(poses):
        cams = [c for _, _, c in p["views"]]
        cl = [[c for c in (S[k][v], F[k][v]) if c is not None] for v in range(NV)]
        if (strict and any(not c for c in cl)) or sum(bool(c) for c in cl) < 2:
            out.append((None, None))
            continue
        use = [v for v in range(NV) if cl[v]]
        best = None
        for combo in itertools.product(*[cl[v] for v in use]):
            X, g, _ = vision.triangulate_n([cams[v] for v in use], list(combo), 1e9 if strict else 0.02)
            if best is None or g < best[1]:
                best = (X, g)
        out.append(best)
    return out


if __name__ == "__main__":
    poses, cache = VI.collect(vision.CAMERAS4, 1280, 960, families=("scara",))
    toks = [random_body(s, "scara").tokens() for s in range(1, 6) for _ in range(40)]
    prompt = vision.structure_prompt(toks[0])
    assert all(vision.structure_prompt(t) == prompt for t in toks)
    base = vision.GeminiPointer(max_calls=900, max_calls_per_min=400)
    ptr = base.with_prompt(prompt, "struct-" + hashlib.sha1(prompt.encode()).hexdigest()[:8])
    flat = [img for p in poses for _, img, _ in p["views"]]
    dets = vision.detect_many(flat, ptr, cache, ptr.cache_name, workers=24)
    print(f"Gemini calls {base.calls}, errors {base.errors}", flush=True)
    S = [[vision.refine_tip(p["views"][v][1], dets[k * NV + v]["uv"])["uv"] if dets[k * NV + v].get("found") else None
          for v in range(NV)] for k, p in enumerate(poses)]
    F = [[vision.chain_end(img, vision.project(cam, np.zeros(3))[0])["uv"] for _, img, cam in p["views"]] for p in poses]
    res = {}
    for strict in (False, True):
        tag = "strict" if strict else "drop 1"
        for name, located in ((f"structure-informed Gemini + snap, {tag}", [tri(poses, k, u, strict) for k, u in enumerate(S)]),
                              (f"chain end walk, {tag}", [tri(poses, k, u, strict) for k, u in enumerate(F)]),
                              (f"either, agreeing combination, {tag}", either(poses, S, F, strict))):
            s = VI.score(poses, located)["scara"]
            res[name] = s
            print(f"{name:45s} accepted {s['accepted']:3d}/200  median "
                  f"{s['median_mm'] if s['median_mm'] is None else round(s['median_mm'], 1)}  p90 "
                  f"{s['p90_mm'] if s['p90_mm'] is None else round(s['p90_mm'], 1)} mm", flush=True)
    json.dump(res, open("results/vision_scara.json", "w"), indent=1)
