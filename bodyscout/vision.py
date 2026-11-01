"""Cameras instead of a marker: GPU rendering (EGL on NVIDIA only), tip detection and triangulation.

Rendering here must happen on the NVIDIA GPU: importing this module fails unless MUJOCO_GL=egl and mujoco
loaded its EGL backend, and every render checks that the active OpenGL context is NVIDIA. No CPU fallback.

CameraRobot has the BlackBoxRobot interface (move, n_channels, limits). It is world side hardware, like the
BlackBoxRobot it wraps: it reads the hidden pose only to RENDER it. What it returns is estimated from the two
images alone: detect the tip in each view, triangulate with the camera matrices. Camera calibration (pose and
field of view, computed from the MuJoCo camera parameters) is allowed; robot geometry is never used.
"""
from __future__ import annotations

import hashlib
import json
import os

if os.environ.get("MUJOCO_GL") != "egl":
    raise RuntimeError(
        f"bodyscout.vision renders on the NVIDIA GPU only: set MUJOCO_GL=egl before starting Python "
        f"(found MUJOCO_GL={os.environ.get('MUJOCO_GL')!r}). CPU rendering (osmesa) is not allowed.")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from .world import ArmSpec, BlackBoxRobot, build_mjcf  # noqa: E402

if mujoco.GLContext.__module__ != "mujoco.egl":  # mujoco was imported earlier with another backend
    raise RuntimeError(f"mujoco picked the {mujoco.GLContext.__module__} backend, not EGL: set "
                       "MUJOCO_GL=egl before anything imports mujoco")

WIDTH, HEIGHT = 640, 480
TARGET = np.array([0.0, 0.0, 0.30])          # centre of the shared workspace, metres
# fixed cameras for every body type: position (m), look-at point, vertical field of view (degrees)
CAMERAS = {
    "front": {"pos": (2.0, 0.0, 0.85), "fovy": 50.0},   # looks along -x
    "side": {"pos": (0.0, -2.0, 0.85), "fovy": 50.0},   # looks along +y
}


# ---- scene ----------------------------------------------------------------------------------
def _xyaxes(pos, target, up=(0.0, 0.0, 1.0)) -> str:
    """MuJoCo camera frame looking from pos at target: the camera looks along its -z, y is up."""
    f = np.asarray(target, float) - np.asarray(pos, float)
    f /= np.linalg.norm(f)
    x = np.cross(f, up)
    x /= np.linalg.norm(x)
    y = np.cross(x, f)
    return " ".join(f"{v:.6f}" for v in (*x, *y))


def scene_xml(spec: ArmSpec, cameras: dict = CAMERAS) -> str:
    """The robot's MJCF wrapped with fixed cameras (world.build_mjcf is not changed)."""
    xml = build_mjcf(spec)
    cams = "".join(f'<camera name="{name}" mode="fixed" pos="{" ".join(f"{p:.4f}" for p in c["pos"])}" '
                   f'xyaxes="{_xyaxes(c["pos"], TARGET)}" fovy="{c["fovy"]}"/>' for name, c in cameras.items())
    return xml.replace("<worldbody>", f"<worldbody>{cams}", 1)


def make_model(spec: ArmSpec, width: int = WIDTH, height: int = HEIGHT, cameras: dict = CAMERAS) -> mujoco.MjModel:
    """Compile the robot plus cameras and size the offscreen framebuffer for width x height renders."""
    model = mujoco.MjModel.from_xml_string(scene_xml(spec, cameras))
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


# ---- GPU checks -------------------------------------------------------------------------------
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


def render(model: mujoco.MjModel, data: mujoco.MjData, width: int = WIDTH, height: int = HEIGHT,
           camera=None) -> tuple[np.ndarray, dict]:
    """One RGB image (height, width, 3) uint8 plus the gl_info() of the context that drew it.
    camera: an MjvCamera, a camera name, or None (a free camera). Raises unless that context is NVIDIA."""
    with mujoco.Renderer(model, height=height, width=width) as r:
        r.update_scene(data, camera=camera if camera is not None else default_camera())
        img = r.render()
        info = gl_info()
    assert_nvidia(info)
    return img, info


# ---- calibration and geometry -----------------------------------------------------------------
def camera_matrices(model: mujoco.MjModel, data: mujoco.MjData, name: str, width: int = WIDTH,
                    height: int = HEIGHT) -> dict:
    """Pinhole calibration of a MuJoCo camera: intrinsics K (pixels; u right, v down, pixel centres at +0.5),
    rotation R (camera to world, columns = camera x, y, z), centre c (m), and the 3x4 projection P."""
    cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, name)
    f = 0.5 * height / np.tan(np.deg2rad(model.cam_fovy[cid]) / 2)
    K = np.array([[f, 0.0, width / 2], [0.0, f, height / 2], [0.0, 0.0, 1.0]])
    R = data.cam_xmat[cid].reshape(3, 3).copy()
    c = data.cam_xpos[cid].copy()
    flip = np.diag([1.0, -1.0, -1.0])  # MuJoCo camera looks along -z with y up; image v grows downward
    P = K @ flip @ np.hstack([R.T, (-R.T @ c)[:, None]])
    return {"K": K, "R": R, "c": c, "P": P, "f": f}


def project(cam: dict, X) -> np.ndarray:
    """World point(s) (..., 3) -> pixel coordinates (..., 2). Points behind the camera give NaN."""
    X = np.atleast_2d(np.asarray(X, float))
    h = (cam["P"] @ np.hstack([X, np.ones((len(X), 1))]).T).T
    uv = h[:, :2] / h[:, 2:3]
    uv[h[:, 2] <= 0] = np.nan
    return uv


def pixel_ray(cam: dict, uv) -> np.ndarray:
    """Unit world direction of the ray through pixel coordinates uv."""
    u, v = uv
    K = cam["K"]
    d_cam = np.array([(u - K[0, 2]) / K[0, 0], -(v - K[1, 2]) / K[1, 1], -1.0])
    d = cam["R"] @ d_cam
    return d / np.linalg.norm(d)


def triangulate(cams: list, uvs: list) -> tuple[np.ndarray, float]:
    """Midpoint of the closest points between two pixel rays. Returns (point (3,), residual m), where the
    residual is the distance between the rays: large when the two detections do not agree."""
    (c1, c2), (d1, d2) = (cams[0]["c"], cams[1]["c"]), (pixel_ray(cams[0], uvs[0]), pixel_ray(cams[1], uvs[1]))
    A = np.array([[d1 @ d1, -d1 @ d2], [d1 @ d2, -d2 @ d2]])
    b = np.array([(c2 - c1) @ d1, (c2 - c1) @ d2])
    s, t = np.linalg.solve(A, b)
    p1, p2 = c1 + s * d1, c2 + t * d2
    return (p1 + p2) / 2, float(np.linalg.norm(p1 - p2))


# ---- detector 1: the red tip sphere -----------------------------------------------------------
def detect_red(img: np.ndarray, min_pixels: int = 6) -> dict:
    """Colour segmentation of the red tip sphere with a sub-pixel centroid.

    A pixel is red when R > 25 and R > 1.5 G and R > 1.5 B, which keeps the sphere's shaded lower half (the
    light is overhead). An unweighted centroid of those pixels: weighting by brightness pulled it about 0.9
    px upward (measured on 110 views; this rule leaves about 0.2 px). Returns {found, uv (pixel coords,
    centres at +0.5) or None, pixels}."""
    rgb = img.astype(np.int32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mask = (r > 25) & (r > 1.5 * g) & (r > 1.5 * b)
    n = int(mask.sum())
    if n < min_pixels:
        return {"found": False, "uv": None, "pixels": n}
    vs, us = np.nonzero(mask)
    return {"found": True, "uv": [float(us.mean() + 0.5), float(vs.mean() + 0.5)], "pixels": n}


DETECTORS = {"color": detect_red}


# ---- cache ------------------------------------------------------------------------------------
class VisionCache:
    """Every image as runs/vision/images/<hash>.png and every detection as runs/vision/detections/
    <hash>.<detector>.json, keyed by a hash of the image bytes. Detections are looked up before running."""

    def __init__(self, root: str = "runs/vision", save_images: bool = True):
        self.root, self.save_images = root, save_images
        os.makedirs(f"{root}/images", exist_ok=True)
        os.makedirs(f"{root}/detections", exist_ok=True)

    @staticmethod
    def key(img: np.ndarray) -> str:
        return hashlib.sha1(np.ascontiguousarray(img).tobytes() + str(img.shape).encode()).hexdigest()[:20]

    def put_image(self, img: np.ndarray) -> str:
        k = self.key(img)
        path = f"{self.root}/images/{k}.png"
        if self.save_images and not os.path.exists(path):
            from PIL import Image
            Image.fromarray(img).save(path, compress_level=1)
        return k

    def detection(self, k: str, detector: str, fn, img: np.ndarray) -> dict:
        path = f"{self.root}/detections/{k}.{detector}.json"
        if os.path.exists(path):
            with open(path) as f:
                return {**json.load(f), "cached": True}
        det = fn(img)
        with open(path, "w") as f:
            json.dump(det, f)
        return {**det, "cached": False}


# ---- the camera robot -------------------------------------------------------------------------
class CameraRobot:
    """Same interface as BlackBoxRobot (move, n_channels, limits), but the tip comes from two cameras.

    move(q) moves the hidden robot (one motion of budget), renders the front and side views of the pose it
    actually reached (backlash and sag included), detects the tip in each image and triangulates. If either
    view cannot see the tip, the result is NaN (no fake value). The robot's own marker reading is discarded.
    `last` holds the latest detections, triangulation residual and image keys for inspection.
    """

    def __init__(self, robot: BlackBoxRobot, detector: str = "color", width: int = WIDTH, height: int = HEIGHT,
                 cameras: dict = CAMERAS, cache: VisionCache | None = None):
        self.robot, self.detector, self.width, self.height = robot, detector, width, height
        self.cameras, self.cache = cameras, cache or VisionCache()
        self._spec, self._renderer = None, None
        self.last: dict = {}

    # ---- hidden: the scene follows the robot's current (possibly damaged) body
    def _sync(self):
        if self._spec is not self.robot._spec:
            if self._renderer is not None:
                self._renderer.close()
            self._spec = self.robot._spec
            self.model = make_model(self._spec, self.width, self.height, self.cameras)
            self.data = mujoco.MjData(self.model)
            self._renderer = mujoco.Renderer(self.model, height=self.height, width=self.width)
            self._renderer.update_scene(self.data, camera=next(iter(self.cameras)))
            self._renderer.render()
            self.gl = gl_info()
            assert_nvidia(self.gl)  # no rendering anywhere but on the NVIDIA GPU
            self._tip = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "tip")
        self.data.qpos[:] = self.robot._data.qpos
        mujoco.mj_forward(self.model, self.data)

    def true_tip(self) -> np.ndarray:
        """The rendered tip position. Scoring only, never for agents."""
        return self.data.site_xpos[self._tip].copy()

    def observe(self) -> np.ndarray:
        """Render both views of the current pose, detect, triangulate."""
        self._sync()
        cams, dets, keys = [], [], []
        for name in self.cameras:
            self._renderer.update_scene(self.data, camera=name)
            img = self._renderer.render()
            k = self.cache.put_image(img)
            keys.append(k)
            dets.append(self.cache.detection(k, self.detector, DETECTORS[self.detector], img))
            cams.append(camera_matrices(self.model, self.data, name, self.width, self.height))
        self.last = {"detections": dict(zip(self.cameras, dets)), "images": dict(zip(self.cameras, keys))}
        if not all(d["found"] for d in dets):
            self.last["residual_m"] = None
            return np.full(3, np.nan)
        X, res = triangulate(cams, [d["uv"] for d in dets])
        self.last["residual_m"] = res
        return X

    # ---- public interface, identical to BlackBoxRobot
    @property
    def n_channels(self) -> int:
        return self.robot.n_channels

    @property
    def limits(self) -> tuple[float, float]:
        return self.robot.limits

    @property
    def motions(self):
        return self.robot.motions

    def move(self, q) -> np.ndarray:
        self.robot.move(q)  # moves the body and spends one motion; its marker reading is discarded
        return self.observe()

    def damage(self, kind: str, seed: int = 0) -> str:
        return self.robot.damage(kind, seed)

    def close(self):
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
