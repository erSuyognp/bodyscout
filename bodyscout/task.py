"""Pick-and-place on a learned body.

TaskPlanner talks only through the blackboard. It reads the current champion and
any high-surprise anomaly (monitor) or holdout score (validator), and it posts
joint targets plus grasp and ungrasp. It never reads the spec, the MuJoCo model,
or a cube pose.

The scorer below is the other half: it places cubes with the true fingertip and
judges where they actually ended. Agents do not call it.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from .agents import Agent
from .blackboard import Blackboard
from .planning import plan
from .world import BlackBoxRobot, Cube, CubeScene

# 8 mm is the monitor's surprise floor. A validator holdout above four times the
# champion's own holdout, and at least this floor, is the same kind of surprise.
HIGH_MM = 8.0
PLACE_TOL_M = 0.03  # 30 mm, hidden success bar
CUBE_SEPARATION_M = 0.08  # farther apart than two grasp radii, so the nearest cube is the right one


def _commands(robot):
    """Every handle the planner is given. Anything else raises AttributeError."""
    return SimpleNamespace(move=robot.move, grasp=robot.grasp, ungrasp=robot.ungrasp,
                           n_channels=robot.n_channels, limits=robot.limits)


class TaskPlanner(Agent):
    """Plans one pick-and-place from the champion currently on the board.

    A monitor anomaly, or a validator score or verdict whose holdout is far
    above the champion's, posts a `replan` artifact and a `replan` need. The
    old waypoint list is dropped. A new plan is posted only once a champion
    newer than that surprise is on the board: for an anomaly, one from a later
    body epoch.

    With a task and no champion, it posts a `trusted-model` need. Grasp and
    ungrasp are `command` artifacts; the contact bit is an observation whose
    parent is that command.
    """

    name = "task-planner"
    HIGH_MM = HIGH_MM

    def __init__(self, robot, seed=0):
        self.robot = robot
        self.seed = seed
        self._task = None
        self._steps = []
        self._i = 0
        self._plan = None
        self._asked = set()
        self.done = False
        self.replanned = False

    def step(self, bb: Blackboard, t: int) -> bool:
        surprises = self._unanswered(bb)
        champ = bb.latest("champion")
        if surprises:
            newest = max(surprises, key=lambda a: a.id)
            if newest.id not in self._asked:
                self._request(bb, newest)
                self._asked.add(newest.id)
                self._plan = None
                self._steps = []
                self._i = 0
                self.done = False  # the waypoint list is stale; a later champion gets a new plan
                self.replanned = True
            if any(not self._answered(champ, s) for s in surprises):
                return True
        if self.done:
            return False
        task = self._ensure_task(bb)
        if task is None:
            return False
        champ = bb.latest("champion")
        if champ is None or "_model" not in champ.payload:
            self._ask_model(bb)
            return False
        if self._plan is None:
            self._build(bb, champ, task, surprises)
        if self._i >= len(self._steps):
            self._finish(bb)
            return True
        self._act(bb, champ)
        if self._i >= len(self._steps):
            self._finish(bb)
        return True

    # -- blackboard ---------------------------------------------------------
    def _threshold(self, bb) -> float:
        champ = bb.latest("champion") or bb.latest("champion", epoch=-1)
        base = self.HIGH_MM
        if champ is not None and champ.payload.get("holdout_mm") not in (None, 0):
            base = float(champ.payload["holdout_mm"])
        return max(4.0 * base, self.HIGH_MM)

    def _high(self, bb):
        """Monitor alarms, and a holdout that got much worse for the crowned model.

        A verdict on some other candidate is often large on purpose. Treating it as
        a body change would throw away the model the validators just crowned.
        """
        thresh = self._threshold(bb)
        out = []
        for art in bb.of("anomaly", epoch=-1):
            p = art.payload
            if float(p.get("surprise_mm", 0)) > float(p.get("threshold_mm", self.HIGH_MM)):
                out.append(art)
        champ = bb.latest("champion") or bb.latest("champion", epoch=-1)
        crowned = None if champ is None else champ.payload.get("candidate")
        for art in bb.of("score", epoch=-1):
            mm = art.payload.get("holdout_mm")
            if mm is not None and float(mm) > thresh:
                out.append(art)
        for art in bb.of("verdict", epoch=-1):
            mm = art.payload.get("holdout_mm")
            if mm is None or float(mm) <= thresh or art.payload.get("replayed") is False:
                continue
            if crowned is not None and art.payload.get("candidate") != crowned:
                continue
            out.append(art)
        return out

    def _unanswered(self, bb):
        have = set(self._plan.parents) if self._plan is not None else set()
        return [a for a in self._high(bb) if a.id not in have]

    @staticmethod
    def _answered(champ, art) -> bool:
        """A later champion answers a surprise. An anomaly also needs a new body epoch,
        because the monitor posts it and then advances the epoch."""
        if champ is None or champ.id <= art.id:
            return False
        if art.kind == "anomaly":
            return champ.epoch > art.epoch
        return champ.epoch >= art.epoch

    def _ask_model(self, bb):
        """One open request. A new epoch closes it, and the next wait posts another."""
        if any(n.open and n.kind == "trusted-model" for n in bb.needs):
            return
        cited = set(self._plan.parents) if self._plan is not None else set()
        if any(n.kind == "trusted-model" and n.id in cited for n in bb.needs):
            return
        parents = [self._task.id] if self._task is not None else []
        bb.need("trusted-model", self.name, 80.0, parents=parents, why="need trusted model")

    def _request(self, bb, art):
        mm = art.payload.get("surprise_mm", art.payload.get("holdout_mm"))
        parents = [art.id] + ([self._plan.id] if self._plan is not None else [])
        bb.post("replan", self.name, {
            "because": art.kind, "source": art.author,
            "surprise_mm": None if mm is None else round(float(mm), 2),
        }, parents)
        bb.need("replan", self.name, 100.0, parents=[art.id],
                why=f"high surprise from {art.author}", surprise=art.id)

    def _ensure_task(self, bb):
        if self._task is None:
            self._task = bb.claim("task")
        return self._task

    def _build(self, bb, champ, task, surprises):
        model = champ.payload["_model"]
        n = self.robot.n_channels
        limits = self.robot.limits
        pick = np.asarray(task.payload["pick"], float)
        place = np.asarray(task.payload["place"], float)
        trial = int(task.payload["trial"])
        steps = []
        for j, (kind, target) in enumerate((("move", pick), ("grasp", None),
                                            ("move", place), ("ungrasp", None))):
            if kind != "move":
                steps.append({"kind": kind})
                continue
            q, info = plan(model, target, n, np.zeros((0, n)), limits,
                           seed=self.seed + 17 * trial + j)
            steps.append({
                "kind": "move",
                "target_m": [round(float(v), 4) for v in target],
                "q": None if q is None else [round(float(v), 6) for v in np.asarray(q, float)],
                "model_err_mm": round(float(info["model_err_m"]) * 1000, 2),
                "refused": info["refused"],
            })
        need = bb.claim("replan")
        model_need = bb.claim("trusted-model")
        parents = [champ.id, task.id] + [s.id for s in surprises]
        for extra in (need, model_need):
            if extra is not None and extra.id not in parents:
                parents.append(extra.id)
        for art in bb.of("replan", epoch=-1):
            if art.id not in parents:
                parents.append(art.id)
        self._steps = steps
        self._i = 0
        self._plan = bb.post("plan", self.name, {"trial": trial, "steps": steps}, parents)

    def _act(self, bb, champ):
        step = self._steps[self._i]
        trial = int(self._task.payload["trial"])
        if step["kind"] == "move":
            if step["refused"] or step["q"] is None:
                bb.post("observation", self.name, {"split": "task", "trial": trial,
                                                   "refused": step["refused"]}, [self._plan.id])
                self._i = len(self._steps)
                return
            q = np.asarray(step["q"], float)
            x = self.robot.move(q)
            pred = champ.payload["_model"].predict(q[None])[0]
            surprise_mm = float(np.linalg.norm(pred - x)) * 1000
            bb.post("observation", self.name, {
                "q": q.tolist(), "x": np.asarray(x, float).tolist(), "split": "task",
                "trial": trial, "surprise_mm": round(surprise_mm, 2),
            }, [self._plan.id])
        else:
            cmd = bb.post("command", self.name, {"command": step["kind"], "trial": trial},
                          [self._plan.id])
            sens = self.robot.grasp() if step["kind"] == "grasp" else self.robot.ungrasp()
            bb.post("observation", self.name, {
                "split": "task", "trial": trial, "gripper": step["kind"],
                "holding": bool(sens["holding"]), "closed": bool(sens["closed"]),
            }, [cmd.id])
        self._i += 1

    def _finish(self, bb):
        if self.done or self._plan is None or self._task is None:
            return
        self.done = True
        obs = [a.id for a in bb.of("observation", epoch=-1) if a.author == self.name]
        parents = [self._plan.id] + (obs[-1:] if obs else [])
        refused = next((s["refused"] for s in self._steps if s.get("refused")), None)
        bb.post("result", self.name, {"trial": int(self._task.payload["trial"]),
                                      "executed": self._i, "steps": len(self._steps),
                                      "refused": refused}, parents)


# ---------------------------------------------------------------------------
# Hidden scorer. Uses the true fingertip and the true cube pose.
# TaskPlanner does not call these.

def sample_scene(robot: BlackBoxRobot, n_cubes: int, seed: int):
    """Held-out cube centres and place points, both on the true workspace."""
    rng = np.random.default_rng(seed)
    lo, hi = robot.limits
    n = robot.n_channels
    picks = []
    for _ in range(80):
        if len(picks) == n_cubes:
            break
        p = robot.true_tip(rng.uniform(lo, hi, n))
        if all(np.linalg.norm(p - q) >= CUBE_SEPARATION_M for q in picks):
            picks.append(np.asarray(p, float))
    if not picks:
        picks.append(np.asarray(robot.true_tip(np.zeros(n)), float))
    places = []
    for i in range(len(picks)):
        place = None
        for _ in range(40):
            cand = np.asarray(robot.true_tip(rng.uniform(lo, hi, n)), float)
            far_from_pick = np.linalg.norm(cand - picks[i]) >= 0.06
            far_from_places = all(np.linalg.norm(cand - p) >= 0.06 for p in places)
            if far_from_pick and far_from_places:
                place = cand
                break
        if place is None:
            place = np.asarray(robot.true_tip(rng.uniform(lo, hi, n)), float)
        places.append(place)
    return picks, places


def score_placement(scene: CubeScene, place, cube_index: int, starts) -> dict:
    """True cube position against the place target. Not an agent observation."""
    cube = scene.cubes[cube_index]
    err = float(np.linalg.norm(cube.pos - np.asarray(place, float)))
    others = all(np.linalg.norm(scene.cubes[i].pos - starts[i]) <= 1e-9
                 for i in range(len(scene.cubes)) if i != cube_index)
    success = (not cube.held) and (not any(c.held for c in scene.cubes)) and others \
        and scene.grasped and err <= PLACE_TOL_M
    return {"success": bool(success), "place_err_mm": err * 1000.0, "holding": bool(cube.held),
            "grasped": bool(scene.grasped), "others_still": bool(others)}


def _run_planner(robot, champion: dict, surprises: list, task: dict, seed: int):
    """Put the champion and the surprise artifacts on a fresh board and run the planner."""
    bb = Blackboard()
    src = bb.post("source", "scorer", {"source": "task", "trial": task["trial"]})
    anomalies = [s for s in surprises if s["kind"] == "anomaly"]
    later = [s for s in surprises if s["kind"] != "anomaly"]
    posted = []
    for s in anomalies:
        posted.append(bb.post(s["kind"], s["author"], dict(s["payload"]), [src.id]))
    if anomalies:
        bb.new_epoch()  # the monitor advances the epoch when it raises an anomaly
    parents = [src.id] + [a.id for a in posted]
    champ = bb.post("champion", "scorer", dict(champion), parents)
    for s in later:  # a validator score newer than the champion stays newer here too
        bb.post(s["kind"], s["author"], dict(s["payload"]), [champ.id])
    bb.need("task", "scorer", 10.0, trial=task["trial"], cube=task["cube"],
            pick=list(task["pick"]), place=list(task["place"]))
    planner = TaskPlanner(_commands(robot), seed=seed)
    for t in range(16):
        planner.step(bb, t)
        if planner.done:
            break
    return bb, planner


def _plan_fields(bb: Blackboard) -> dict:
    art = bb.latest("plan", epoch=-1)
    if art is None:
        return {"model_err_mm": None, "refused": "replan open" if bb.has_need("replan") else "no plan"}
    errs = [s["model_err_mm"] for s in art.payload["steps"] if "model_err_mm" in s]
    reasons = [s["refused"] for s in art.payload["steps"] if s.get("refused")]
    return {"model_err_mm": max(errs) if errs else None, "refused": reasons[0] if reasons else ""}


def evaluate_phase(spec, champion, surprises, seed: int, n_trials: int = 1, n_cubes: int = 3) -> list:
    """Score held-out pick-and-place trials on a fresh robot. `spec` is ground truth."""
    blank = {"success": False, "place_err_mm": None, "holding": False, "grasped": False,
             "others_still": False, "replan_requested": bool(surprises), "model_err_mm": None,
             "refused": "no champion"}
    if champion is None or champion.get("_model") is None:
        return [{**blank, "trial": i} for i in range(n_trials)]
    probe = BlackBoxRobot(spec, seed=seed)
    picks, places = sample_scene(probe, n_cubes, seed)
    rows = []
    for i in range(n_trials):
        k = i % len(picks)
        robot = BlackBoxRobot(spec, seed=seed)
        scene = CubeScene([Cube(f"cube{j}", p) for j, p in enumerate(picks)])
        starts = [c.pos.copy() for c in scene.cubes]
        robot.attach_scene(scene)
        task = {"trial": i, "cube": k, "pick": picks[k].tolist(), "place": places[k].tolist()}
        bb, planner = _run_planner(robot, champion, surprises, task, seed + i)
        scored = score_placement(scene, places[k], k, starts)
        scored.update(_plan_fields(bb))
        scored["trial"] = i
        scored["replan_requested"] = bool(planner.replanned)
        rows.append(scored)
    return rows
