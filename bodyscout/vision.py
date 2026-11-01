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

from .blackboard import Blackboard  # noqa: E402
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
# four views: the two above plus one from behind on the other side and one from high up
CAMERAS4 = {**CAMERAS,
            "back": {"pos": (-1.414, 1.414, 0.85), "fovy": 50.0},
            "high": {"pos": (1.1, 1.1, 1.9), "fovy": 50.0}}


# ---- scene ----------------------------------------------------------------------------------
def _xyaxes(pos, target, up=(0.0, 0.0, 1.0)) -> str:
    """MuJoCo camera frame looking from pos at target: the camera looks along its -z, y is up."""
    f = np.asarray(target, float) - np.asarray(pos, float)
    f /= np.linalg.norm(f)
    x = np.cross(f, up)
    x /= np.linalg.norm(x)
    y = np.cross(x, f)
    return " ".join(f"{v:.6f}" for v in (*x, *y))


TIP_RGBA, LINK_RGBA = 'rgba="0.9 0.3 0.2 1"', 'rgba="0.3 0.5 0.8 1"'  # as drawn by world.build_mjcf


def scene_xml(spec: ArmSpec, cameras: dict = CAMERAS, markerless: bool = False) -> str:
    """The robot's MJCF wrapped with fixed cameras (world.build_mjcf is not changed). markerless=True paints
    the tip sphere in the link colour, so there is no marker to find."""
    xml = build_mjcf(spec)
    if markerless:
        assert TIP_RGBA in xml, "tip colour changed in world.build_mjcf"
        xml = xml.replace(TIP_RGBA, LINK_RGBA)
    cams = "".join(f'<camera name="{name}" mode="fixed" pos="{" ".join(f"{p:.4f}" for p in c["pos"])}" '
                   f'xyaxes="{_xyaxes(c["pos"], TARGET)}" fovy="{c["fovy"]}"/>' for name, c in cameras.items())
    return xml.replace("<worldbody>", f"<worldbody>{cams}", 1)


def make_model(spec: ArmSpec, width: int = WIDTH, height: int = HEIGHT, cameras: dict = CAMERAS,
               markerless: bool = False) -> mujoco.MjModel:
    """Compile the robot plus cameras and size the offscreen framebuffer for width x height renders."""
    model = mujoco.MjModel.from_xml_string(scene_xml(spec, cameras, markerless))
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


def triangulate_n(cams: list, uvs: list, gap_m: float = 0.02) -> tuple[np.ndarray, float, list]:
    """Least squares point closest to N pixel rays. The residual ("gap") is twice the largest distance from
    the point to a ray, which for two views equals the distance between the rays (as in triangulate()).
    With more than two views, the view whose ray is farthest away is dropped while the gap exceeds gap_m
    (one confused view gets outvoted). Returns (point, gap in m over the views kept, indices kept)."""
    keep = list(range(len(cams)))
    while True:
        cs = np.array([cams[i]["c"] for i in keep])
        ds = np.array([pixel_ray(cams[i], uvs[i]) for i in keep])
        A = sum(np.eye(3) - np.outer(d, d) for d in ds)
        b = sum((np.eye(3) - np.outer(d, d)) @ c for c, d in zip(cs, ds))
        X = np.linalg.solve(A, b)
        dist = [float(np.linalg.norm((np.eye(3) - np.outer(d, d)) @ (X - c))) for c, d in zip(cs, ds)]
        worst = int(np.argmax(dist))
        if len(keep) <= 2 or 2 * dist[worst] <= gap_m:
            return X, 2 * float(max(dist)), keep
        keep.pop(worst)


# ---- image-only refinement: snap a rough point to the end cap of the link it sits on --------------
ROBOT_RGB_RULE = "B > 50 and B > R + 25 and B > G + 5 (the links are blue; floor, shadow and sky are grey or black)"


def refine_tip(img: np.ndarray, uv, radius: float | None = None) -> dict:
    """Move a rough tip point onto the end of the link it lies on, using the image only (no robot geometry).

    Robot pixels near uv are segmented by colour; the local link direction comes from their principal axis;
    the end cap is the extreme of the component along that axis on uv's side; the tip centre sits one
    half-width (the cap's radius, measured in the image) inside that extreme. Falls back to uv when there is
    no robot blob nearby or the blob has no clear direction (link pointing at the camera).

    The snap may move the point at most one cap diameter (2 x the measured half width, at least 6 px at
    640 wide): a refinement that helps moves the point a pixel or two, while larger jumps had landed on another
    link or the wrong end (diagnosed on 1200 views of arms, gantries and telescopes)."""
    from scipy import ndimage

    h, w = img.shape[:2]
    R = radius or 30.0 * w / 640
    u0, v0 = float(uv[0]), float(uv[1])
    x0, x1 = int(max(0, u0 - R)), int(min(w, u0 + R + 1))
    y0, y1 = int(max(0, v0 - R)), int(min(h, v0 + R + 1))
    if x1 - x0 < 3 or y1 - y0 < 3:
        return {"uv": [u0, v0], "refined": False, "why": "outside image"}
    win = img[y0:y1, x0:x1].astype(np.int32)
    r, g, b = win[..., 0], win[..., 1], win[..., 2]
    mask = (b > 50) & (b > r + 25) & (b > g + 5)
    lab, n = ndimage.label(mask)
    if n == 0:
        return {"uv": [u0, v0], "refined": False, "why": "no robot pixels nearby"}
    vs, us = np.nonzero(lab)
    du = us + x0 + 0.5 - u0
    dv = vs + y0 + 0.5 - v0
    d2 = du ** 2 + dv ** 2
    if d2.min() > (12.0 * w / 640) ** 2:
        return {"uv": [u0, v0], "refined": False, "why": "nearest robot pixel too far"}
    comp = lab[vs[np.argmin(d2)], us[np.argmin(d2)]]
    sel = lab[vs, us] == comp
    P = np.stack([us[sel] + x0 + 0.5, vs[sel] + y0 + 0.5], axis=1)
    near = P[np.linalg.norm(P - [u0, v0], axis=1) <= 18.0 * w / 640]
    if len(near) < 8:
        return {"uv": [u0, v0], "refined": False, "why": "too few pixels"}
    mu = near.mean(0)
    evals, evecs = np.linalg.eigh(np.cov((near - mu).T))
    if evals[1] < 2.5 * max(evals[0], 1e-9):
        return {"uv": [u0, v0], "refined": False, "why": "no clear link direction"}
    d = evecs[:, 1]
    proj = (P - mu) @ d
    side = np.sign(([u0, v0] - mu) @ d) or 1.0
    ext = proj.max() if side > 0 else proj.min()
    cap = P[np.abs(proj - ext) <= 6.0 * w / 640]
    perp = (cap - mu) @ np.array([-d[1], d[0]])
    half = max(1.0, (perp.max() - perp.min()) / 2)
    lateral = (perp.max() + perp.min()) / 2
    tip = mu + d * (ext - side * half) + np.array([-d[1], d[0]]) * lateral
    shift = float(np.linalg.norm(tip - [u0, v0]))
    if shift > max(2 * half, 6.0 * w / 640):
        return {"uv": [u0, v0], "refined": False, "why": f"snap of {shift:.1f} px is larger than the cap",
                "half_width_px": float(half)}
    return {"uv": [float(tip[0]), float(tip[1])], "refined": True, "half_width_px": float(half), "shift_px": shift}


def chain_end(img: np.ndarray, base_uv) -> dict:
    """Where the robot's chain ends in the image, from the image alone: segment robot pixels, start at the robot
    pixel nearest the mount point (the projection of the world origin, i.e. camera calibration, not robot
    geometry), and walk through connected robot pixels; the pixel farthest along that walk is the chain's end,
    refined to its end cap. Breaks down when links overlap in the image or the walk is cut by an occlusion."""
    from collections import deque
    h, w = img.shape[:2]
    rgb = img.astype(np.int32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mask = (b > 50) & (b > r + 25) & (b > g + 5)
    vs, us = np.nonzero(mask)
    if len(vs) < 20 or base_uv is None or not np.all(np.isfinite(base_uv)):
        return {"found": False, "uv": None}
    k = int(np.argmin((us + 0.5 - base_uv[0]) ** 2 + (vs + 0.5 - base_uv[1]) ** 2))
    dist = np.full(mask.shape, -1, np.int32)
    q = deque([(vs[k], us[k])])
    dist[vs[k], us[k]] = 0
    far = (vs[k], us[k])
    while q:
        y, x = q.popleft()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and dist[yy, xx] < 0:
                    dist[yy, xx] = dist[y, x] + 1
                    q.append((yy, xx))
                    if dist[yy, xx] > dist[far]:
                        far = (yy, xx)
    end = [far[1] + 0.5, far[0] + 0.5]
    return {"found": True, "uv": refine_tip(img, end)["uv"], "walk_px": int(dist[far])}


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


# ---- detector 2: Gemini Robotics ER points at the end of the last link ----------------------------
GEMINI_PROMPT = ("Point to the tip of the robot: the free end of its last link, the end farthest along the chain "
                 "from the base on the floor. Answer only with JSON: [{\"point\": [y, x], \"label\": \"tip\"}] "
                 "where y and x are normalized to 0-1000.")


GEMINI_PROMPT_MULTI = ("Point to up to 3 places that could be this robot's end effector: the free end of its last "
                       "link, where a gripper or tool would attach. Order them from most to least likely. Answer "
                       "only with JSON: [{\"point\": [y, x], \"label\": \"candidate 1\"}, ...] where y and x "
                       "are normalized to 0-1000.")
GEMINI_PROMPT_ZOOM = ("This is a close-up crop of a robot. Point to the tip of the robot: the free end of its last "
                      "link. Answer only with JSON: [{\"point\": [y, x], \"label\": \"tip\"}] where y and x are "
                      "normalized to 0-1000 within this crop.")
GEMINI_PROMPT_EFFECTOR = ("Point to this robot's end effector: the very end of the arm, where a gripper or tool "
                          "would be mounted. It is the free end of the chain of links that starts at the base on "
                          "the floor, not a joint in the middle. Answer only with JSON: [{\"point\": [y, x], "
                          "\"label\": \"end effector\"}] where y and x are normalized to 0-1000.")
GEMINI_PROMPT_CHAIN = ("Follow this robot's links from its base on the floor, joint by joint, to the free end of the "
                       "chain. Point to that free end: the end of the last link, the point farthest from the base "
                       "along the links (not the highest point and not a joint). Answer only with JSON: "
                       "[{\"point\": [y, x], \"label\": \"free end\"}] where y and x are normalized to 0-1000.")


def structure_prompt(tokens) -> str:
    """A pointing question that uses what the swarm has learned about the body: structure tokens such as
    ["hz", "hz", "sz", "hz"] (h = rotates, s = slides; axis x, y or z, z = vertical) become a description of
    the chain from the base, and Gemini is asked for the end of the last link. No geometry (lengths, poses)."""
    def say(t):
        kind, ax = t[0], t[1]
        if ax not in "xyz":
            return "a joint whose motion could not be seen yet"
        if kind == "h":
            return "a joint that rotates about the vertical axis" if ax == "z" else "a joint that rotates about a horizontal axis"
        return "a joint that slides vertically (up and down)" if ax == "z" else "a joint that slides horizontally"
    steps = "; ".join(f"{i + 1}) {say(t)}" for i, t in enumerate(tokens))
    return (f"Starting from its base on the floor, this robot has {len(tokens)} joints in a chain: {steps}. "
            f"Each joint is followed by a link. Point to the free end of the link after joint {len(tokens)}, the "
            "very end of the chain where a tool would be mounted. Answer only with JSON: [{\"point\": [y, x], "
            "\"label\": \"end\"}] where y and x are normalized to 0-1000.")


ZOOM = 4  # the crop is (width / ZOOM) x (height / ZOOM) pixels, enlarged ZOOM times before asking


def zoom_crop(img: np.ndarray, uv) -> tuple[np.ndarray, tuple[int, int]]:
    """A (h/ZOOM, w/ZOOM) crop centred on uv (clamped inside the image), enlarged ZOOM times; returns the
    enlarged crop and the crop's top left pixel."""
    from PIL import Image
    h, w = img.shape[:2]
    cw, ch = w // ZOOM, h // ZOOM
    x0 = int(np.clip(round(uv[0] - cw / 2), 0, w - cw))
    y0 = int(np.clip(round(uv[1] - ch / 2), 0, h - ch))
    crop = Image.fromarray(img[y0:y0 + ch, x0:x0 + cw]).resize((w, h), Image.LANCZOS)
    return np.asarray(crop), (x0, y0)


def find_robotics_er_model(client) -> str:
    """The exact Gemini Robotics ER model id this key can use (prefers the non streaming preview)."""
    names = [m.name for m in client.models.list() if "robotics-er" in m.name.lower()]
    if not names:
        raise RuntimeError("no Gemini Robotics ER model visible to this GEMINI_API_KEY")
    plain = [n for n in names if "streaming" not in n]
    return sorted(plain or names)[-1]


class CallCapReached(RuntimeError):
    pass


class GeminiPointer:
    """Asks Gemini Robotics ER to point at the robot's tip in one image; returns normalized [y, x] (0-1000) as
    pixel coordinates. Retries once on an error; raises CallCapReached once `max_calls` real calls are spent
    (cached answers are free). Thread safe, so many images can be asked in parallel."""

    name = "gemini"

    def __init__(self, model: str | None = None, max_calls: int = 2000, temperature: float = 0.0,
                 retry_wait_s: float = 3.0, prompt: str = GEMINI_PROMPT, tag: str = "",
                 max_calls_per_min: float | None = None):
        import threading

        from google import genai

        from .env import load_env

        load_env()
        # BODYSCOUT_VISION_GEMINI_KEY lets the detector use Gemini while LLM hypothesizers stay off
        # (they switch on for GEMINI_API_KEY), e.g. for bit-for-bit repeatable demo runs.
        key = os.environ.get("BODYSCOUT_VISION_GEMINI_KEY") or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY (or BODYSCOUT_VISION_GEMINI_KEY) is not set (put it in .env)")
        self.client = genai.Client(api_key=key)
        self.model = model or find_robotics_er_model(self.client)
        self.max_calls, self.temperature, self.retry_wait_s = max_calls, temperature, retry_wait_s
        self.prompt, self.tag, self.max_calls_per_min = prompt, tag, max_calls_per_min
        self.calls, self.errors = 0, 0
        self._lock = threading.Lock()
        self._next_slot = 0.0

    @property
    def cache_name(self) -> str:
        return f"gemini-{self.model.split('/')[-1]}{('-' + self.tag) if self.tag else ''}"

    def with_prompt(self, prompt: str, tag: str) -> "GeminiPointer":
        """A pointer sharing this one's client, call budget and pacing, but asking another question."""
        import copy
        other = copy.copy(self)
        other.prompt, other.tag = prompt, tag
        other._parent = self
        return other

    def _root(self) -> "GeminiPointer":
        return getattr(self, "_parent", self)

    def _pace(self):
        """Spread calls out to stay under max_calls_per_min (the event's spend rule)."""
        import time
        root = self._root()
        if not root.max_calls_per_min:
            return
        with root._lock:
            now = time.time()
            slot = max(now, root._next_slot)
            root._next_slot = slot + 60.0 / root.max_calls_per_min
        time.sleep(max(0.0, slot - now))

    def _ask(self, png: bytes) -> str:
        from google.genai import types
        r = self.client.models.generate_content(
            model=self.model, contents=[types.Part.from_bytes(data=png, mime_type="image/png"), self.prompt],
            config=types.GenerateContentConfig(temperature=self.temperature))
        return r.text or ""

    @staticmethod
    def parse(text: str, width: int, height: int) -> dict:
        import re
        m = re.search(r"\[.*\]", text, re.S)
        try:
            pts = json.loads(m.group(0)) if m else []
            cands = [[float(p["point"][1]) / 1000 * width, float(p["point"][0]) / 1000 * height]
                     for p in pts if isinstance(p, dict) and len(p.get("point", [])) == 2]
            if not cands:
                raise ValueError("no point")
            return {"found": True, "uv": cands[0], "candidates": cands[:3], "raw": text.strip()}
        except (ValueError, KeyError, IndexError, TypeError):
            return {"found": False, "uv": None, "candidates": [], "raw": text.strip()}

    def __call__(self, img: np.ndarray) -> dict:
        import io
        import time

        from PIL import Image
        root = self._root()
        with root._lock:
            if root.calls >= root.max_calls:
                raise CallCapReached(f"Gemini call cap of {root.max_calls} reached")
            root.calls += 1
        self._pace()
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, format="PNG")
        for attempt in (0, 1):  # retry once
            try:
                det = self.parse(self._ask(buf.getvalue()), img.shape[1], img.shape[0])
                return {**det, "model": self.model}
            except Exception as e:  # noqa: BLE001 (network, quota, server errors)
                with root._lock:
                    root.errors += 1
                if attempt == 0:
                    time.sleep(self.retry_wait_s)
                else:
                    raise RuntimeError(f"Gemini failed twice: {type(e).__name__}: {e}") from e


def detect_many(images: list, fn, cache: "VisionCache", cache_name: str, workers: int = 16) -> list:
    """Detect in many images at once (threads), reading and writing the cache by image hash.
    Failures (errors, call cap) come back as {found: False, error: ...} and are not cached."""
    from concurrent.futures import ThreadPoolExecutor

    keys = [cache.put_image(img) for img in images]

    def one(i):
        try:
            return cache.detection(keys[i], cache_name, fn, images[i])
        except Exception as e:  # noqa: BLE001
            return {"found": False, "uv": None, "error": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, range(len(images))))


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


# ---- bad observations stay out of the data --------------------------------------------------------
class CameraBlackboard(Blackboard):
    """Blackboard for camera input: a non finite reading (the tip was hidden, or the views disagreed) is filed
    as a `bad_observation` artifact (same payload and parents, so the provenance stays complete) instead of an
    `observation`, so no modeler trains on it and no validator scores on it."""

    def post(self, kind, author, payload, parents=None):
        if kind == "observation" and "x" in payload and not np.all(np.isfinite(payload["x"])):
            kind = "bad_observation"
        return super().post(kind, author, payload, parents)


# ---- feedback: what the swarm has learned steers what the camera looks for -------------------------
class GazeAgent:
    """Closes the loop between learning and seeing. Watches the board for the body's structure (channel agents'
    findings, or the crowned chain model's structure), and when it knows more than the camera does, tells the
    camera what kind of body it is looking at (CameraRobot.look_for: a structure-informed Gemini question), posts
    a `gaze` artifact citing the findings or champion it used, and opens a new epoch so that readings taken while
    the camera may have been looking at the wrong part stop counting (the same mechanism as the Monitor's "my
    body changed"). It changes the camera's question at most `max_switches` times per run.

    Agent rules: it reads only the board; its only robot access is the camera control look_for (no move, no
    hidden state)."""

    name = "gaze"

    def __init__(self, camera, max_switches: int = 2, min_findings_frac: float = 0.75):
        self.camera, self.max_switches, self.min_frac = camera, max_switches, min_findings_frac
        self.switches, self.current = 0, None

    def _structure(self, bb):
        champs = [a for a in bb.of("champion") if a.payload.get("family") == "chain"]
        if champs and "structure" in (champs[-1].payload.get("describe") or {}):
            return list(champs[-1].payload["describe"]["structure"]), [champs[-1].id], "champion"
        findings = {a.payload["channel"]: a for a in bb.of("finding")}
        n = self.camera.n_channels
        if len(findings) >= max(2, int(self.min_frac * n)):
            toks = []
            for ch in range(n):
                f = findings.get(ch)
                toks.append(f.payload["type"] + f.payload["axis"] if f and f.payload["type"] in "hs" else "h?")
            return toks, [a.id for a in findings.values()], "findings"
        return None, [], None

    def step(self, bb, t):
        if self.switches >= self.max_switches:
            return False
        toks, parents, source = self._structure(bb)
        if not toks or toks == self.current:
            return False
        tag = self.camera.look_for(toks)
        self.current = toks
        self.switches += 1
        bb.post("gaze", self.name, {"structure": toks, "source": source, "prompt_tag": tag,
                                    "switch": self.switches}, parents)
        bb.new_epoch()  # earlier readings may have tracked the wrong part: relearn from what the camera sees now
        bb.need("data", self.name, 100.0, why="camera now looks for the end of the learned chain")
        return True


# ---- the camera robot -------------------------------------------------------------------------
class CameraRobot:
    """Same interface as BlackBoxRobot (move, n_channels, limits), but the tip comes from two cameras.

    move(q) moves the hidden robot (one motion of budget), renders the front and side views of the pose it
    actually reached (backlash and sag included), detects the tip in each image and triangulates. If either
    view cannot see the tip, the result is NaN (no fake value). The robot's own marker reading is discarded.

    detector: "color" (detector 1, needs the red marker) or "gemini" (detector 2, Gemini Robotics ER).
    max_gap_mm: when the two views' rays miss each other by more than this, the views disagree about where the
    tip is; the reading is a bad observation and comes back as NaN (so it is never mistaken for a body change).
    With more than two cameras, a disagreeing view is dropped first (triangulate_n); drop_views=False instead
    rejects the reading unless every view agrees (stricter, fewer wrong readings get through).
    pipeline (gemini only): "point" asks once per view; "refine" snaps that point to the link's end cap in the
    image; "zoom" asks again on a 4x close-up around the first point, then refines; "multi" asks for up to 3
    candidates per view, refines each, and keeps the combination whose rays agree best.
    markerless=True paints the tip like the links. With "gemini", a failed detection falls back to detector 1
    only in marker mode; markerless has nothing to fall back on. `last` holds the latest detections,
    triangulation residual and image keys.
    """

    def __init__(self, robot: BlackBoxRobot, detector: str = "color", markerless: bool = False,
                 width: int = WIDTH, height: int = HEIGHT, cameras: dict = CAMERAS,
                 cache: VisionCache | None = None, pointer: GeminiPointer | None = None,
                 max_gap_mm: float | None = 20.0, pipeline: str = "point", drop_views: bool = True):
        if detector not in ("color", "gemini"):
            raise ValueError(detector)
        if markerless and detector == "color":
            raise ValueError("markerless mode has no red marker: use detector='gemini'")
        if pipeline not in ("point", "refine", "zoom", "multi"):
            raise ValueError(pipeline)
        self.pipeline, self.drop_views = pipeline, drop_views
        self.robot, self.detector, self.markerless, self.max_gap_mm = robot, detector, markerless, max_gap_mm
        self.width, self.height, self.cameras = width, height, cameras
        self.cache = cache or VisionCache()
        self.pointer = pointer if pointer is not None or detector != "gemini" else GeminiPointer()
        self._spec, self._renderer = None, None
        self.last: dict = {}
        self._atexit = False

    # ---- hidden: the scene follows the robot's current (possibly damaged) body
    def _sync(self):
        if self._spec is not self.robot._spec:
            if self._renderer is not None:
                self._renderer.close()
            self._spec = self.robot._spec
            self.model = make_model(self._spec, self.width, self.height, self.cameras, self.markerless)
            self.data = mujoco.MjData(self.model)
            self._renderer = mujoco.Renderer(self.model, height=self.height, width=self.width)
            if not self._atexit:  # registered AFTER mujoco's EGL exit hook, so it runs BEFORE the display is
                import atexit     # terminated (atexit is last in, first out); avoids EGL errors at exit
                atexit.register(self.close)
                self._atexit = True
            self._renderer.update_scene(self.data, camera=next(iter(self.cameras)))
            self._renderer.render()
            self.gl = gl_info()
            assert_nvidia(self.gl)  # no rendering anywhere but on the NVIDIA GPU
            self._tip = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "tip")
        self.data.qpos[:] = self.robot._data.qpos
        mujoco.mj_forward(self.model, self.data)

    def look_for(self, tokens) -> str:
        """Camera control (no hidden information flows back): ask Gemini about a body with this structure from
        now on (see structure_prompt). Returns the prompt's cache tag."""
        import hashlib
        prompt = structure_prompt(tokens)
        tag = "struct-" + hashlib.sha1(prompt.encode()).hexdigest()[:8]
        base = self.pointer._root() if hasattr(self.pointer, "_root") else self.pointer
        self.pointer = base.with_prompt(prompt, tag)
        self.hint = list(tokens)
        return tag

    def true_tip(self, q=None) -> np.ndarray:
        """Scoring only, never for agents. With q: the hidden robot's noise free tip for command q (what
        swarm.run's scorer asks). Without q: the tip position in the last rendered pose."""
        if q is not None:
            return self.robot.true_tip(q)
        return self.data.site_xpos[self._tip].copy()

    def render_views(self) -> list:
        """[(camera name, image, camera matrices)] of the current pose."""
        self._sync()
        out = []
        for name in self.cameras:
            self._renderer.update_scene(self.data, camera=name)
            out.append((name, self._renderer.render().copy(),
                        camera_matrices(self.model, self.data, name, self.width, self.height)))
        return out

    def _detect(self, img: np.ndarray) -> dict:
        if self.detector == "color":
            return {**self.cache.detection(self.cache.put_image(img), "color", detect_red, img), "by": "color"}
        k = self.cache.put_image(img)
        if self.pipeline == "multi":
            mp = self.pointer.with_prompt(GEMINI_PROMPT_MULTI, "multi")
            try:
                det = {**self.cache.detection(k, mp.cache_name, mp, img), "by": "gemini multi"}
            except Exception as e:  # noqa: BLE001
                det = {"found": False, "uv": None, "error": f"{type(e).__name__}: {e}", "by": "gemini multi"}
            if det["found"]:
                cands = det.get("candidates") or [det["uv"]]
                det["candidates"] = [refine_tip(img, c)["uv"] for c in cands]
                det["uv"] = det["candidates"][0]
        else:
            try:
                det = {**self.cache.detection(k, self.pointer.cache_name, self.pointer, img), "by": "gemini"}
            except Exception as e:  # noqa: BLE001 (two failed calls or the call cap)
                det = {"found": False, "uv": None, "error": f"{type(e).__name__}: {e}", "by": "gemini"}
            if det["found"] and self.pipeline == "zoom":
                zp = self.pointer.with_prompt(GEMINI_PROMPT_ZOOM, "zoom")
                crop, (x0, y0) = zoom_crop(img, det["uv"])
                try:
                    zd = self.cache.detection(self.cache.put_image(crop), zp.cache_name, zp, crop)
                except Exception:  # noqa: BLE001 (keep the first point)
                    zd = {"found": False}
                if zd.get("found"):
                    det = {**det, "coarse": det["uv"], "uv": [x0 + zd["uv"][0] / ZOOM, y0 + zd["uv"][1] / ZOOM]}
            if det["found"] and self.pipeline in ("refine", "zoom"):
                det = {**det, "unrefined": det["uv"], "uv": refine_tip(img, det["uv"])["uv"]}
        if not det["found"] and not self.markerless:  # fall back to detector 1 only when the marker is there
            det = {**self.cache.detection(k, "color", detect_red, img), "by": "color (fallback)"}
        return det

    def locate(self, views: list, dets: list) -> np.ndarray:
        """Triangulate from per view detections (or NaN if fewer than two views saw the tip, or the views
        disagree); fills `last`. With candidate lists ("multi"), the combination whose rays agree best wins."""
        import itertools
        self.last = {"detections": {n: d for (n, _, _), d in zip(views, dets)},
                     "images": {n: self.cache.key(img) for n, img, _ in views}, "residual_m": None}
        seen = [i for i, d in enumerate(dets) if d["found"]]
        if len(seen) < 2 or (len(views) == 2 and len(seen) < 2):
            missing = [n for (n, _, _), d in zip(views, dets) if not d["found"]]
            self.last["bad"] = "tip not found in " + ", ".join(missing)
            return np.full(3, np.nan)
        cams = [views[i][2] for i in seen]
        cand = [dets[i].get("candidates") or [dets[i]["uv"]] for i in seen]
        gap_m = (self.max_gap_mm or 1e9) / 1000 if self.drop_views else 1e9  # 1e9: never drop a view
        best = None
        for combo in itertools.product(*cand):
            X, res, keep = triangulate_n(cams, list(combo), gap_m)
            score = res + 0.002 * (len(seen) - len(keep))
            if best is None or score < best[0]:
                best = (score, X, res, combo, keep)
        _, X, res, combo, keep = best
        for j, i in enumerate(seen):  # the point actually used per view (for drawing)
            dets[i]["used_uv"] = list(combo[j]) if j in keep else None
        self.last["residual_m"] = res
        self.last["views_used"] = [views[seen[j]][0] for j in keep]
        if self.max_gap_mm is not None and res * 1000 > self.max_gap_mm:
            self.last["bad"] = f"views disagree: rays {res * 1000:.0f} mm apart"
            return np.full(3, np.nan)
        return X

    def observe(self) -> np.ndarray:
        """Render both views of the current pose, detect, triangulate."""
        views = self.render_views()
        if self.detector == "gemini":  # both views at once: half the wait
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(views)) as ex:
                dets = list(ex.map(self._detect, [img for _, img, _ in views]))
        else:
            dets = [self._detect(img) for _, img, _ in views]
        return self.locate(views, dets)

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
