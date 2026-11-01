"""Which question makes Gemini find the end of the chain, SCARA included? Run on the Brev GPU instance:

    MUJOCO_GL=egl python experiments/vision_prompts.py [--families scara] [--prompts effector chain structure]

Same 200 poses per family as vision_accuracy.py (2 cameras, 640x480, markerless). Every prompt's point is snapped
to the link's end cap (refine_tip) and triangulated; readings whose rays miss by more than 20 mm are rejected.
Prompts:
  tip        the V2 question (answers cached)
  effector   "the end effector, where a gripper or tool would be mounted, not a joint in the middle"
  chain      "follow the links from the base to the free end of the chain"
  structure  describes the body's structure tokens (hz, sz, ...) and asks for the end of the last link. Here the
             tokens are the TRUE ones, standing in for what the swarm discovers: an upper bound for the feedback
             loop in which the swarm's own structure hypothesis steers the camera.
"""
import argparse
import hashlib
import json
import os
import sys
import time

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # vision_improve

import numpy as np  # noqa: E402

import vision_improve as VI  # noqa: E402
from bodyscout import vision  # noqa: E402
from bodyscout.world import FAMILIES, random_body  # noqa: E402

R = "results"


def body_tokens(fam, n_poses=200, n_bodies=5):
    """True structure per pose, in collect()'s order (scorer side only)."""
    return [random_body(seed, fam).tokens() for seed in range(1, n_bodies + 1) for _ in range(n_poses // n_bodies)]


def write_summary(path="results/summary_vision.md"):
    import re
    f = lambda v: "n/a" if v is None else f"{v:.1f}"  # noqa: E731
    pr = json.load(open(f"{R}/vision_prompts.json")) if os.path.exists(f"{R}/vision_prompts.json") else {}
    sc = json.load(open(f"{R}/vision_scara.json")) if os.path.exists(f"{R}/vision_scara.json") else {}
    names = {"tip": "\"point to the tip\" (V2 question)", "effector": "\"point to the end effector, where a tool is mounted\"",
             "chain": "\"follow the links from the base to the free end\"",
             "structure": "structure-informed: the body's joint list, then \"point to the end of the last link\""}
    L = ["## Telling the camera what it is looking at: SCARA (V6)", "",
         "SCARA is where markerless fails: Gemini points at the top of the vertical shaft. Same 200 SCARA poses, "
         "markerless, every point snapped to the link's end cap; median / 90th percentile error on accepted readings "
         "(accepted out of 200). The structure-informed question uses the TRUE structure here, standing in for what "
         "the swarm discovers (an upper bound for the feedback loop below).", "",
         "| question to Gemini, 2 cameras 640x480 | SCARA |", "| --- | --- |"]
    for k in ("tip", "effector", "chain", "structure"):
        if k in pr and "scara" in pr[k]:
            x = pr[k]["scara"]
            L.append(f"| {names[k]} | {f(x['median_mm'])} / {f(x['p90_mm'])} ({x['accepted']}/{x['n']}) |")
    mo = json.load(open(f"{R}/vision_motion.json")) if os.path.exists(f"{R}/vision_motion.json") else {}
    if mo:
        fams = list(next(iter(mo.values())))
        L += ["", "Active perception, no Gemini: nudge each channel in turn; the robot pixels that change under every "
              "nudge are the last link; its tip end is where the most distal channel's sweep concentrates (2 cameras, "
              "all families, n_channels + 1 renders per reading, so a calibration tool on a real robot):", "",
              "| | " + " | ".join(fams) + " |", "| --- |" + " --- |" * len(fams)]
        for k, res in mo.items():
            L.append(f"| motion only, {k} | " + " | ".join(
                f"{f(res[x]['median_mm'])} / {f(res[x]['p90_mm'])} ({res[x]['accepted']}/{res[x]['n']})" for x in fams) + " |")
    if sc:
        L += ["", "| 4 cameras 1280x960 | SCARA |", "| --- | --- |"]
        for k, x in sc.items():
            L.append(f"| {k} | {f(x['median_mm'])} / {f(x['p90_mm'])} ({x['accepted']}/{x['n']}) |")
    L += ["", "What this shows: generic rewordings do not help. Telling Gemini the body's structure cuts the median "
          "from about 200 mm to 61 mm (2 cameras), and to 7 mm when all 4 views must agree, but a minority of readings "
          "are wrong in the same way in every view, so no geometric check removes them and the 90th percentile stays "
          "near 300 mm. Walking the robot's pixels to the chain's end finds the tip more often (median 14.7 mm) but "
          "has its own tail. Active perception (what moves when every joint moves) gives the best SCARA tail by "
          "far (median 12.6, 90th percentile 30 mm, against about 300 mm for every Gemini question) but is worse "
          "than Gemini on arms and telescopes; it costs extra motions per reading. SCARA is therefore much better "
          "located than before but not at marker level, and no single detector is best for every body.",
          "",
          "Feedback loop at swarm level (condition \"improved + gaze feedback loop\" below): a GazeAgent turns the "
          "swarm's discovered structure into the camera's question and opens a new epoch so earlier readings stop "
          "counting. It made learning WORSE: each switch restarts learning and the 64 motion budget ran out before a "
          "new model (telescopes: no model, against 5.1 and 10.7 mm without it); on gantries it sometimes steered "
          "by a wrong structure; on SCARA it never fired because too many readings were rejected for the channel "
          "agents to finish. The loop needs a design that keeps data across a switch, or a larger budget.", ""]
    txt = open(path).read()
    txt = re.sub(r"\n## Telling the camera what it is looking at: SCARA \(V6\).*?(?=\n## |\Z)", "", txt, flags=re.S)
    parts = re.split(r"(\n## Swarm learns from cameras)", txt, maxsplit=1)
    txt = parts[0].rstrip() + "\n\n" + "\n".join(L) + ("".join(parts[1:]) if len(parts) > 1 else "")
    open(path, "w").write(txt)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", nargs="+", default=list(FAMILIES))
    ap.add_argument("--prompts", nargs="+", default=["tip", "effector", "chain", "structure"])
    ap.add_argument("--max-calls", type=int, default=6000)
    ap.add_argument("--calls-per-min", type=float, default=400)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--summary", action="store_true", help="only write the summary section")
    a = ap.parse_args()
    if a.summary:
        write_summary()
        sys.exit(0)
    t0 = time.time()
    base = vision.GeminiPointer(max_calls=a.max_calls, max_calls_per_min=a.calls_per_min)
    out_path = f"{R}/vision_prompts.json"
    saved = json.load(open(out_path)) if os.path.exists(out_path) else {}
    poses, cache = VI.collect(vision.CAMERAS, 640, 480, families=a.families)
    toks = [t for fam in a.families for t in body_tokens(fam)]
    nv = 2
    for name in a.prompts:
        if name == "structure":  # one prompt per pose (the body's structure); group by prompt text
            dets = [None] * (len(poses) * nv)
            for prompt in sorted(set(vision.structure_prompt(t) for t in toks)):
                tag = "struct-" + hashlib.sha1(prompt.encode()).hexdigest()[:8]
                ptr = base.with_prompt(prompt, tag)
                idx = [k for k, t in enumerate(toks) if vision.structure_prompt(t) == prompt]
                imgs = [img for k in idx for _, img, _ in poses[k]["views"]]
                got = vision.detect_many(imgs, ptr, cache, ptr.cache_name, workers=a.workers)
                for j, k in enumerate(idx):
                    dets[k * nv:(k + 1) * nv] = got[j * nv:(j + 1) * nv]
        else:
            prompt = {"tip": vision.GEMINI_PROMPT, "effector": vision.GEMINI_PROMPT_EFFECTOR,
                      "chain": vision.GEMINI_PROMPT_CHAIN}[name]
            ptr = base if name == "tip" else base.with_prompt(prompt, name)
            dets = vision.detect_many([img for p in poses for _, img, _ in p["views"]], ptr, cache, ptr.cache_name,
                                      workers=a.workers)
        located = []
        for k, p in enumerate(poses):
            uvs = []
            for v, (_, img, cam) in enumerate(p["views"]):
                d = dets[k * nv + v]
                uvs.append(vision.refine_tip(img, d["uv"])["uv"] if d and d.get("found") else None)
            if any(u is None for u in uvs):
                located.append((None, None))
            else:
                X, gap, _ = vision.triangulate_n([c for _, _, c in p["views"]], uvs, 1e9)
                located.append((X, gap))
        res = VI.score(poses, located)
        for fam, sres in res.items():
            saved.setdefault(name, {})[fam] = sres
        print(f"{name:10s} calls so far {base.calls:5d} ({time.time() - t0:.0f}s) | " + " | ".join(
            f"{f}: {s['accepted']}/{s['n']} ok, {s['median_mm'] if s['median_mm'] is None else round(s['median_mm'], 1)}"
            f"/{s['p90_mm'] if s['p90_mm'] is None else round(s['p90_mm'], 1)} mm" for f, s in res.items()), flush=True)
        json.dump(saved, open(out_path, "w"), indent=1)
    print(f"total {time.time() - t0:.0f}s, Gemini calls {base.calls}, errors {base.errors}")
