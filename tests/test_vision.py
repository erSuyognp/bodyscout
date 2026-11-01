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
