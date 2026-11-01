"""GPU rendering smoke test. Rendering runs in a subprocess with MUJOCO_GL=egl, because mujoco picks its GL
backend once at import and other test modules import mujoco first. Skipped only when no NVIDIA GPU is present."""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _has_nvidia_gpu() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    out = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
    return out.returncode == 0 and "GPU" in out.stdout


def _python(code: str, env_update: dict, drop=()) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_update)
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT,
                          timeout=300)


def test_import_refuses_without_egl():
    r = _python("import bodyscout.vision", {}, drop=("MUJOCO_GL",))
    assert r.returncode != 0 and "MUJOCO_GL=egl" in r.stderr
    r = _python("import bodyscout.vision", {"MUJOCO_GL": "osmesa"})
    assert r.returncode != 0 and "osmesa" in r.stderr


@pytest.mark.skipif(not _has_nvidia_gpu(), reason="no NVIDIA GPU present")
def test_render_on_nvidia_gpu():
    code = (
        "import json\n"
        "from bodyscout import vision\n"
        "from bodyscout.world import random_body\n"
        "m = vision.make_model(random_body(1, 'arm'))\n"
        "img, info = vision.render(m, vision.pose(m))\n"
        "print(json.dumps({'shape': list(img.shape), 'std': float(img.std()), **info}))\n")
    r = _python(code, {"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["shape"] == [480, 640, 3]
    assert out["std"] > 5, "blank image"
    assert "NVIDIA" in out["gl_renderer"].upper(), out
    assert "NVIDIA" in out["gl_vendor"].upper(), out


@pytest.mark.skipif(not _has_nvidia_gpu(), reason="no NVIDIA GPU present")
def test_camera_robot_triangulates_tip():
    code = (
        "import json, numpy as np\n"
        "from bodyscout import vision\n"
        "from bodyscout.world import BlackBoxRobot, random_body\n"
        "robot = BlackBoxRobot(random_body(2, 'scara'), seed=2)\n"
        "cam = vision.CameraRobot(robot, cache=vision.VisionCache('runs/vision_test', save_images=False))\n"
        "rng = np.random.default_rng(3)\n"
        "errs, nan = [], 0\n"
        "for _ in range(12):\n"
        "    x = cam.move(rng.uniform(*cam.limits, cam.n_channels))\n"
        "    if np.isnan(x).any():\n"
        "        nan += 1\n"
        "    else:\n"
        "        errs.append(float(np.linalg.norm(x - cam.true_tip())) * 1000)\n"
        "out = {'n': cam.n_channels, 'limits': list(cam.limits), 'motions': robot.motions, 'nan': nan,\n"
        "       'median_mm': float(np.median(errs)), 'max_mm': float(np.max(errs)), 'gl': cam.gl['gl_renderer']}\n"
        "cam.close()\n"
        "print(json.dumps(out))\n")
    r = _python(code, {"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["n"] == 4 and out["limits"] == [-2.0, 2.0] and out["motions"] == 12
    assert out["nan"] <= 3 and out["median_mm"] < 8 and out["max_mm"] < 25, out
    assert "NVIDIA" in out["gl"].upper()


@pytest.mark.skipif(not _has_nvidia_gpu(), reason="no NVIDIA GPU present")
def test_markerless_and_gemini_fallback_rules():
    code = (
        "import json, numpy as np\n"
        "from bodyscout import vision\n"
        "from bodyscout.world import BlackBoxRobot, random_body\n"
        "class Broken:\n"
        "    cache_name = 'broken'\n"
        "    def __call__(self, img):\n"
        "        raise RuntimeError('no network in tests')\n"
        "cache = vision.VisionCache('runs/vision_test', save_images=False)\n"
        "robot = BlackBoxRobot(random_body(2, 'scara'), seed=2)\n"
        "robot.move(np.array([0.5, -0.4, 0.3, 0.2]))\n"
        "plain = vision.CameraRobot(robot, detector='gemini', markerless=True, cache=cache, pointer=Broken())\n"
        "views = plain.render_views()\n"
        "red = [vision.detect_red(img)['found'] for _, img, _ in views]\n"
        "x_plain = plain.observe()\n"
        "marked = vision.CameraRobot(robot, detector='gemini', markerless=False, cache=cache, pointer=Broken())\n"
        "x_marked = marked.observe()\n"
        "by = [d['by'] for d in marked.last['detections'].values()]\n"
        "p = vision.GeminiPointer.parse('```json\\n[{\"point\": [360, 492], \"label\": \"tip\"}]\\n```', 640, 480)\n"
        "print(json.dumps({'red_in_markerless': red, 'plain_nan': bool(np.isnan(x_plain).all()),\n"
        "    'marked_ok': bool(np.isfinite(x_marked).all()), 'by': by, 'uv': p['uv']}))\n")
    r = _python(code, {"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["red_in_markerless"] == [False, False]      # no marker to find
    assert out["plain_nan"]                                # markerless: no fallback, no fake point
    assert out["marked_ok"] and out["by"] == ["color (fallback)"] * 2
    assert out["uv"] == pytest.approx([492 / 1000 * 640, 360 / 1000 * 480])


def test_markerless_needs_gemini():
    r = _python("from bodyscout import vision\nfrom bodyscout.world import BlackBoxRobot, random_body\n"
                "vision.CameraRobot(BlackBoxRobot(random_body(1, 'arm')), detector='color', markerless=True)",
                {"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"})
    assert r.returncode != 0 and ("use detector='gemini'" in r.stderr or "EGL" in r.stderr or "egl" in r.stderr)


@pytest.mark.skipif(not _has_nvidia_gpu(), reason="no NVIDIA GPU present")
def test_refine_triangulate_n_and_pipelines():
    code = (
        "import json, numpy as np\n"
        "from bodyscout import vision\n"
        "from bodyscout.world import BlackBoxRobot, random_body\n"
        # synthetic image: a blue horizontal link ending in a round cap centred at (300.5, 200.5), radius 4
        "img = np.zeros((480, 640, 3), np.uint8)\n"
        "yy, xx = np.mgrid[0:480, 0:640]\n"
        "link = (np.abs(yy + 0.5 - 200.5) <= 3) & (xx + 0.5 >= 250) & (xx + 0.5 <= 300.5)\n"
        "cap = (xx + 0.5 - 300.5) ** 2 + (yy + 0.5 - 200.5) ** 2 <= 16\n"
        "img[link | cap] = (76, 128, 204)\n"
        "near = vision.refine_tip(img, [302.0, 202.0])\n"
        "far = vision.refine_tip(img, [262.0, 200.0])\n"
        # N view triangulation: 2 views equal triangulate(); a third, confused view is dropped
        "robot = BlackBoxRobot(random_body(1, 'gantry'), seed=1)\n"
        "robot.move(np.array([0.3, -0.2, 0.4, 0.5]))\n"
        "cam = vision.CameraRobot(robot, detector='gemini', markerless=True, pointer=False,\n"
        "                         cameras=vision.CAMERAS4, cache=vision.VisionCache('runs/vision_test', save_images=False))\n"
        "views = cam.render_views(); t = cam.true_tip()\n"
        "mats = [c for _, _, c in views]\n"
        "uvs = [vision.project(m, t)[0] for m in mats]\n"
        "X2, g2 = vision.triangulate(mats[:2], uvs[:2]); Xn, gn, k = vision.triangulate_n(mats[:2], uvs[:2])\n"
        "bad = list(uvs); bad[2] = bad[2] + np.array([60.0, -40.0])\n"
        "Xb, gb, kb = vision.triangulate_n(mats, bad)\n"
        "class Fake:\n"
        "    cache_name = 'fake'\n"
        "    def with_prompt(self, p, tag):\n"
        "        return self\n"
        "    def __call__(self, im):\n"
        "        return {'found': True, 'uv': [320.0, 240.0], 'candidates': [[320.0, 240.0], [100.0, 100.0]]}\n"
        "out = {}\n"
        "for pipe in ('refine', 'multi'):\n"
        "    c = vision.CameraRobot(robot, detector='gemini', markerless=True, pointer=Fake(), pipeline=pipe,\n"
        "                           cache=vision.VisionCache('runs/vision_test', save_images=False), max_gap_mm=None)\n"
        "    x = c.observe(); out[pipe] = bool(np.isfinite(x).all()); c.close()\n"
        "cam.close()\n"
        "print(json.dumps({'near': near, 'far_refined': far['refined'], 'same2': bool(np.allclose(X2, Xn) and abs(g2 - gn) < 1e-9),\n"
        "    'kept': kb, 'err_mm': float(np.linalg.norm(Xb - t) * 1000), 'pipelines': out}))\n")
    r = _python(code, {"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["near"]["refined"] and out["near"]["uv"] == pytest.approx([300.5, 200.5], abs=1.0), out["near"]
    assert not out["far_refined"]               # a 38 px jump is larger than the cap: keep the input point
    assert out["same2"]                          # two views: identical to triangulate()
    assert out["kept"] == [0, 1, 3] and out["err_mm"] < 1.0   # the confused third view is outvoted
    assert out["pipelines"] == {"refine": True, "multi": True}


@pytest.mark.skipif(not _has_nvidia_gpu(), reason="no NVIDIA GPU present")
def test_gaze_agent_feedback_loop():
    code = (
        "import json\n"
        "from bodyscout import vision\n"
        "from bodyscout.blackboard import Blackboard\n"
        "p = vision.structure_prompt(['hz', 'sz', 'h?'])\n"
        "class Cam:\n"
        "    n_channels = 3\n"
        "    def __init__(self):\n"
        "        self.asked = []\n"
        "    def look_for(self, toks):\n"
        "        self.asked.append(list(toks)); return 'tag'\n"
        "cam = Cam(); g = vision.GazeAgent(cam, max_switches=2)\n"
        "bb = Blackboard()\n"
        "before = g.step(bb, 0)\n"
        "f0 = bb.post('finding', 'channel-0', {'channel': 0, 'type': 'h', 'axis': 'z'})\n"
        "f1 = bb.post('finding', 'channel-1', {'channel': 1, 'type': 's', 'axis': 'z'})\n"
        "f2 = bb.post('finding', 'channel-2', {'channel': 2, 'type': '?', 'axis': '?'})\n"
        "first = g.step(bb, 1)\n"
        "gaze = bb.of('gaze', epoch=-1)[0]\n"
        "bb.post('finding', 'channel-0', {'channel': 0, 'type': 'h', 'axis': 'z'})\n"
        "bb.post('finding', 'channel-1', {'channel': 1, 'type': 's', 'axis': 'z'})\n"
        "bb.post('finding', 'channel-2', {'channel': 2, 'type': 'h', 'axis': 'y'})\n"
        "second = g.step(bb, 2)\n"
        "bb.post('finding', 'channel-2', {'channel': 2, 'type': 'h', 'axis': 'x'})\n"
        "third = g.step(bb, 3)\n"
        "print(json.dumps({'prompt_ok': 'slides vertically' in p and 'could not be seen' in p and 'after joint 3' in p,\n"
        "    'before': before, 'first': first, 'asked': cam.asked, 'parents': sorted(gaze.parents),\n"
        "    'finding_ids': sorted([f0.id, f1.id, f2.id]), 'epoch': bb.epoch, 'second': second, 'third': third}))\n")
    r = _python(code, {"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["prompt_ok"]
    assert out["before"] is False and out["first"] is True           # nothing to say until channels report
    assert out["asked"][0] == ["hz", "sz", "h?"]                     # unseen channel stays unknown, not guessed
    assert out["parents"] == out["finding_ids"]                      # the gaze artifact cites the findings
    assert out["second"] is True and out["third"] is False and out["epoch"] == 2   # at most 2 switches
