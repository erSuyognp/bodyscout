"""GPU rendering of the hidden world through EGL on an NVIDIA GPU. Scoring and drawing only.

Rendering here must happen on the NVIDIA GPU: importing this module fails unless MUJOCO_GL=egl, and
assert_nvidia() fails unless the active OpenGL context reports NVIDIA. There is no CPU (osmesa) fallback.

Like planning.reach_errors, this module builds the true MJCF to draw the robot; agents never import it.
"""
from __future__ import annotations

import os

if os.environ.get("MUJOCO_GL") != "egl":
    raise RuntimeError(
        f"bodyscout.vision renders on the NVIDIA GPU only: set MUJOCO_GL=egl before starting Python "
        f"(found MUJOCO_GL={os.environ.get('MUJOCO_GL')!r}). CPU rendering (osmesa) is not allowed.")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from .world import ArmSpec, build_mjcf  # noqa: E402

if mujoco.GLContext.__module__ != "mujoco.egl":  # mujoco was imported earlier with another backend
    raise RuntimeError(f"mujoco picked the {mujoco.GLContext.__module__} backend, not EGL: set "
                       "MUJOCO_GL=egl before anything imports mujoco")


def make_model(spec: ArmSpec, width: int = 640, height: int = 480) -> mujoco.MjModel:
    """Compile the robot and size the offscreen framebuffer for width x height renders."""
    model = mujoco.MjModel.from_xml_string(build_mjcf(spec))
    model.vis.global_.offwidth = max(int(model.vis.global_.offwidth), width)
    model.vis.global_.offheight = max(int(model.vis.global_.offheight), height)
    return model


def default_camera(lookat=(0.0, 0.0, 0.2), distance: float = 1.1, azimuth: float = 135.0,
                   elevation: float = -25.0) -> mujoco.MjvCamera:
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = lookat
    cam.distance, cam.azimuth, cam.elevation = distance, azimuth, elevation
    return cam


def pose(model: mujoco.MjModel, q=None) -> mujoco.MjData:
    """Data with joint positions q (radians or metres; zeros if None), kinematics computed."""
    data = mujoco.MjData(model)
    if q is not None:
        data.qpos[:] = np.asarray(q, float)
    mujoco.mj_forward(model, data)
    return data


def gl_info() -> dict:
    """Vendor, renderer and version strings of the CURRENT OpenGL context, plus the EGL display's vendor.
    Call while a mujoco.Renderer's context is current (right after creating or rendering with it)."""
    from OpenGL import EGL, GL

    def s(x):
        return x.decode() if isinstance(x, bytes) else str(x)

    info = {"gl_vendor": s(GL.glGetString(GL.GL_VENDOR)), "gl_renderer": s(GL.glGetString(GL.GL_RENDERER)),
            "gl_version": s(GL.glGetString(GL.GL_VERSION))}
    display = EGL.eglGetCurrentDisplay()
    if display:
        info["egl_vendor"] = s(EGL.eglQueryString(display, EGL.EGL_VENDOR))
        info["egl_version"] = s(EGL.eglQueryString(display, EGL.EGL_VERSION))
    return info


def assert_nvidia(info: dict) -> None:
    """Fail unless the active context is NVIDIA hardware (not llvmpipe, osmesa or any CPU renderer)."""
    if "NVIDIA" not in info.get("gl_vendor", "").upper() or "NVIDIA" not in info.get("gl_renderer", "").upper():
        raise RuntimeError(f"rendering is not on an NVIDIA GPU: {info}")


def render(model: mujoco.MjModel, data: mujoco.MjData, width: int = 640, height: int = 480,
           camera: mujoco.MjvCamera | None = None) -> tuple[np.ndarray, dict]:
    """One RGB image (height, width, 3) uint8 plus the gl_info() of the context that drew it.
    Raises unless that context is NVIDIA."""
    with mujoco.Renderer(model, height=height, width=width) as r:
        r.update_scene(data, camera=camera or default_camera())
        img = r.render()
        info = gl_info()
    assert_nvidia(info)
    return img, info
