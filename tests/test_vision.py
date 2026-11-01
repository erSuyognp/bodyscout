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
