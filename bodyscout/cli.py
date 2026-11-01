"""Command line. ``python -m bodyscout learn --robot path.py:Class --budget N``."""
from __future__ import annotations

import os

# Pin BLAS before numpy. Threaded reductions change least-squares fits run to run.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import importlib.util
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bodyscout")
    sub = parser.add_subparsers(dest="cmd", required=True)
    learn = sub.add_parser("learn", help="run the swarm, then export the crowned chain")
    learn.add_argument("--robot", required=True, help="path.py:Class, constructed with no arguments")
    learn.add_argument("--budget", required=True, type=int, help="motion budget for the swarm")
    learn.add_argument("--out", default="export", help="directory for robot.urdf, robot.xml, body.json, report.html")
    learn.add_argument("--seed", type=int, default=0)
    learn.add_argument("--unknown", action="store_true",
                       help="body type unknown: channel agents decide hinge or slide")
    learn.add_argument("--llm", action="store_true",
                       help="ask LLM hypothesizers when an API key is set")
    learn.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "learn":
        cmd_learn(args)
    return 0


def load_robot(spec: str):
    """Import ``path.py:Class`` and construct it with no arguments.

    The last colon separates the class name, so a Windows drive letter is kept.
    """
    path_s, sep, cls_name = spec.rpartition(":")
    if not sep or not path_s or not cls_name:
        raise SystemExit(f"--robot must be path.py:Class, got {spec!r}")
    path = Path(path_s)
    if not path.is_file():
        raise SystemExit(f"robot file not found: {path}")
    parent = str(path.resolve().parent)
    if parent not in sys.path:
        sys.path.append(parent)
    mod_name = "bodyscout_user_robot"
    loaded = importlib.util.spec_from_file_location(mod_name, path)
    if loaded is None or loaded.loader is None:
        raise SystemExit(f"cannot import {path}")
    module = importlib.util.module_from_spec(loaded)
    try:
        loaded.loader.exec_module(module)
    except Exception as exc:
        raise SystemExit(f"importing {path} failed: {exc}") from exc
    cls = getattr(module, cls_name, None)
    if cls is None:
        raise SystemExit(f"{cls_name} is not in {path}")
    try:
        robot = cls()
    except Exception as exc:
        raise SystemExit(f"could not construct {cls_name}(): {exc}") from exc
    missing = [name for name in ("move", "n_channels", "limits", "true_tip", "motions")
               if not hasattr(robot, name)]
    if missing:
        raise SystemExit(
            f"{cls_name} is missing {', '.join(missing)}. "
            "It needs the black-box surface (move, n_channels, limits), a motions counter, "
            "and true_tip so the learning curve can be scored."
        )
    try:
        n = int(robot.n_channels)
        lo, hi = robot.limits
        lo, hi = float(lo), float(hi)
    except Exception as exc:
        raise SystemExit(f"{cls_name} n_channels and limits could not be read: {exc}") from exc
    if isinstance(robot.n_channels, bool) or n < 1:
        raise SystemExit(f"{cls_name}.n_channels must be a positive int")
    if not lo < hi:
        raise SystemExit(f"{cls_name}.limits must be a low, high pair")
    return robot


def cmd_learn(args) -> None:
    if args.budget < 1:
        raise SystemExit("--budget must be a positive number of motions")
    from .export import export_chain
    from .models import ChainModel
    from .swarm import run

    if args.llm:
        from .env import load_env
        load_env()
        use_llm = None  # one hypothesizer per provider that has a key
    else:
        use_llm = False
    robot = load_robot(args.robot)
    out = run(robot, condition="swarm", budget=args.budget, eval_at=(args.budget,),
              n_targets=8, seed=args.seed, use_llm=use_llm, unknown_body=args.unknown,
              max_ticks=max(400, args.budget * 8), verbose=args.verbose)
    bb = out["blackboard"]
    champ = bb.latest("champion")
    family = None if champ is None else champ.payload.get("family")
    model = None if champ is None else champ.payload.get("_model")
    if not isinstance(model, ChainModel):
        fitted = sorted({a.payload.get("family") for a in bb.of("model", epoch=-1)})
        raise SystemExit(
            f"no crowned chain model to export "
            f"(latest champion: {family}, models fit: {fitted or 'none'}, motions: {out['motions']}). "
            f"Raise --budget."
        )
    meta = {
        "robot": args.robot,
        "budget": args.budget,
        "seed": args.seed,
        "motions": out["motions"],
        "holdout_mm": None if champ.payload.get("holdout_mm") is None else float(champ.payload["holdout_mm"]),
        "n_holdout": champ.payload.get("n_holdout"),
        "votes": champ.payload.get("votes"),
        "unknown_body": bool(args.unknown),
        "crowned": True,
        "champion_id": champ.id,
    }
    written = export_chain(model, args.out, meta)
    tree = written["tree"]
    hold = meta["holdout_mm"]
    hold_s = "no holdout yet" if hold is None else f"holdout {hold:.2f} mm"
    print(f"crowned chain {tree['structure_channel_order']}, {hold_s}, {meta['motions']} motions")
    n_marked = sum(j["length_identifiable"] is False for j in tree["joints"])
    n_marked += tree["tip"]["length_identifiable"] is False
    if n_marked:
        print(f"{n_marked} length(s) marked non-identifiable")
    for key in ("urdf", "mjcf", "body", "report"):
        print(f"wrote {written[key]}")
