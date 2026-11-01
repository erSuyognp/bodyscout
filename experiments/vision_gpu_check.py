"""V0: prove MuJoCo renders on the NVIDIA GPU through EGL. Run on the Brev GPU instance:

    MUJOCO_GL=egl python experiments/vision_gpu_check.py

1. nvidia-smi must list an NVIDIA GPU, else stop.
2. Render one 640x480 image of random_body(1, "arm") -> runs/vision/check.png.
3. Print the OpenGL vendor / renderer and EGL vendor of the active context (must name NVIDIA).
4. Render 200 frames while nvidia-smi samples the GPU's process list; show this python process in it.
5. Report frames per second.
"""
import os
import shutil
import subprocess
import sys
import time

if shutil.which("nvidia-smi") is None or subprocess.run(["nvidia-smi", "-L"], capture_output=True).returncode != 0:
    sys.exit("STOP: no NVIDIA GPU found (nvidia-smi missing or failing). This check must run on the Brev GPU "
             "instance; CPU rendering is not allowed.")
print(subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout.strip())

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from bodyscout import vision  # noqa: E402  (raises unless MUJOCO_GL=egl)
from bodyscout.world import random_body  # noqa: E402

W, H, N = 640, 480, 200
spec = random_body(1, "arm")
model = vision.make_model(spec, W, H)
data = vision.pose(model, np.linspace(-0.6, 0.8, model.nq))

# ---- one image ---------------------------------------------------------------------------
img, info = vision.render(model, data, W, H)
os.makedirs("runs/vision", exist_ok=True)
try:
    from PIL import Image
    Image.fromarray(img).save("runs/vision/check.png")
except ImportError:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.imsave("runs/vision/check.png", img)
print(f"saved runs/vision/check.png  shape={img.shape}  mean pixel={img.mean():.1f}")
for k, v in info.items():
    print(f"{k:12s} {v}")

# ---- 200 frames, with nvidia-smi sampling during the loop ------------------------------------
pid = os.getpid()
cam = vision.default_camera()
with mujoco.Renderer(model, height=H, width=W) as r:
    r.update_scene(data, camera=cam)
    r.render()  # warm up
    vision.assert_nvidia(vision.gl_info())
    smi = subprocess.Popen(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    t0 = time.perf_counter()
    q0 = data.qpos.copy()
    for i in range(N):
        data.qpos[:] = q0 + 0.5 * np.sin(0.05 * i + np.arange(model.nq))  # the arm moves every frame
        mujoco.mj_forward(model, data)
        r.update_scene(data, camera=cam)
        frame = r.render()  # reads the pixels back, so each frame waits for the GPU
    dt = time.perf_counter() - t0
    in_loop = smi.poll() is None
    smi_out, _ = smi.communicate()
    print(f"\n{N} frames {W}x{H} in {dt:.3f} s = {N / dt:.0f} frames per second "
          f"(nvidia-smi {'was still sampling at the end of' if in_loop else 'finished during'} the loop)")

print("\nnvidia-smi during the render loop:")
print(smi_out)
rows = [ln for ln in smi_out.splitlines() if f" {pid} " in ln]
if rows:
    print(f"this python process (pid {pid}) on the GPU:")
    print("\n".join(rows))
else:
    sys.exit(f"FAIL: pid {pid} does not appear in nvidia-smi's process list")
