"""Write a crowned ChainModel as URDF, MJCF, body.json, and a short HTML report.

Geometry is the parameter vector ``predict`` uses (``model.params``), in chain
order. ``model.order[i]`` is the channel that drives link ``i``. A revolute
joint position is that channel's command in radians. A prismatic joint position
is metres: the fitted axis length times the command. The swarm reports link
lengths from ``report_params``, the shortest equivalent body. Joint origins in
these files stay on ``model.params``.

Masses are placeholders. A length ``ChainModel.identifiable`` marks false is
commented in the URDF and the MJCF.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

import numpy as np

from .models import ChainModel

PLACEHOLDER_MASS_KG = 0.1
_HINGE_LIMIT = 3.141592653589793


def export_chain(model: ChainModel, out_dir, meta: dict | None = None) -> dict:
    """Write ``robot.urdf``, ``robot.xml``, ``body.json``, and ``report.html``."""
    tree = kinematic_tree(model, meta)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "dir": str(out),
        "urdf": str(out / "robot.urdf"),
        "mjcf": str(out / "robot.xml"),
        "body": str(out / "body.json"),
        "report": str(out / "report.html"),
    }
    _write(paths["urdf"], render_urdf(tree))
    _write(paths["mjcf"], render_mjcf(tree))
    _write(paths["body"], json.dumps(tree, indent=2) + "\n")
    _write(paths["report"], render_report(tree))
    paths["tree"] = tree
    return paths


def kinematic_tree(model: ChainModel, meta: dict | None = None) -> dict:
    """Joint tree in chain order, rounded the same way the XML files are."""
    if not isinstance(model, ChainModel):
        raise TypeError("export expects a ChainModel")
    if getattr(model, "tree", False):
        raise ValueError("export writes one serial chain, and this ChainModel is a branched fit")
    if model.params is None:
        raise ValueError("ChainModel has no parameters to export")
    n = int(model.n)
    p = np.asarray(model.params, float).reshape(-1)
    if p.size != 6 * n + 3:
        raise ValueError(f"expected {6 * n + 3} parameters, got {p.size}")
    order = [int(c) for c in model.order]
    if sorted(order) != list(range(n)):
        raise ValueError(f"chain order {order} is not a permutation of channels")
    types = [str(t) for t in model.types]
    if len(types) != n or any(t not in ("h", "s") for t in types):
        raise ValueError(f"joint types must be 'h' or 's' per channel, got {types}")
    offs, angs, tip = model._unpack(p)
    flags = None if model.identifiable is None else list(model.identifiable)
    joints = []
    for i in range(n):
        slide = types[i] == "s"
        axis, gain = _axis_and_gain(angs[i], slide)
        origin = [_r(x) for x in offs[i]]
        limit = _slide_limit(gain) if slide else (-_HINGE_LIMIT, _HINGE_LIMIT)
        joints.append({
            "name": f"j{i}_c{order[i]}",
            "link": f"link{i}_c{order[i]}",
            "chain_index": i,
            "channel": order[i],
            "type": "prismatic" if slide else "revolute",
            "origin_m": origin,
            "axis": [_r(x) for x in axis],
            "metres_per_command": _r(gain),
            "limit": [_r(limit[0]), _r(limit[1])],
            "limit_unit": "m" if slide else "rad",
            "length_m": _r(float(np.linalg.norm(origin))),
            # identifiable[i - 1] is offs[i]. The base offset offs[0] is not in that list.
            "length_identifiable": None if i == 0 else _flag(flags, i - 1),
        })
    tip_origin = [_r(x) for x in tip]
    tree = {
        "family": "chain",
        "n_channels": n,
        "chain_order": order,
        "structure_channel_order": [str(t) for t in model.tokens()],
        "placeholder_mass_kg": PLACEHOLDER_MASS_KG,
        "masses": "placeholder",
        "joints": joints,
        "tip": {
            "name": "tip_link",
            "joint": "tip",
            "site": "tip",
            "type": "fixed",
            "origin_m": tip_origin,
            "length_m": _r(float(np.linalg.norm(tip_origin))),
            "length_identifiable": _flag(flags, n - 1),
        },
        "shortest_equivalent_differs": _shortest_differs(model, p, offs, tip),
        "describe": model.describe() if model.report_params is not None else None,
        "run": dict(meta or {}),
    }
    return _jsonable(tree)


def render_urdf(tree: dict) -> str:
    mass = tree["placeholder_mass_kg"]
    lines = [
        '<?xml version="1.0"?>',
        '<robot name="bodyscout">',
        "<!-- BodyScout kinematic export of a crowned chain model.",
        "     One link and one joint per channel, in chain order from the base to the tip.",
        "     A revolute joint position is the channel command in radians.",
        "     A prismatic joint position is in metres: metres_per_command times the command",
        "     (the scale is in the comment on that joint and in body.json).",
        f"     placeholder mass: {_mass(mass)} kg, not identified. Inertias, effort and velocity are placeholders too.",
        '     "non-identifiable length: <link>" marks an origin the training motions could not pin.',
        "     Dynamics were not identified. -->",
    ]
    _link_xml(lines, "base", mass, 0.012, 1)
    parent = "base"
    for joint in tree["joints"]:
        _link_xml(lines, joint["link"], mass, 0.012, 1)
        _joint_xml(lines, joint, parent, joint["link"], 1)
        parent = joint["link"]
    tip = tree["tip"]
    _link_xml(lines, tip["name"], mass, 0.015, 1)
    _fixed_xml(lines, tip, parent, 1)
    lines.append("</robot>")
    lines.append("")
    return "\n".join(lines)


def render_mjcf(tree: dict) -> str:
    mass = _mass(tree["placeholder_mass_kg"])
    lines = [
        '<?xml version="1.0"?>',
        '<mujoco model="bodyscout">',
        '<compiler angle="radian"/>',
        '<option timestep="0.002" gravity="0 0 0"><flag contact="disable"/></option>',
        "<!-- BodyScout kinematic export of a crowned chain model.",
        "     One link and one joint per channel, in chain order from the base to the tip.",
        "     A revolute joint's qpos is the channel command in radians.",
        "     A prismatic joint's qpos is metres = metres_per_command * command,",
        "     stored as the custom numeric {joint name}_metres_per_command.",
        f"     placeholder mass: {mass} kg, not identified.",
        '     "non-identifiable length: <link>" marks an origin the training motions could not pin.',
        "     Dynamics were not identified. Gravity is off. -->",
        "<worldbody>",
    ]
    depth = 1
    for joint in tree["joints"]:
        if joint["length_identifiable"] is False:
            lines.append(_ind(depth, f"<!-- non-identifiable length: {joint['link']} -->"))
        lines.append(_ind(depth, f"<!-- {_scale_comment(joint)} -->"))
        lines.append(_ind(depth, f'<body name="{joint["link"]}" pos="{_vec(joint["origin_m"])}">'))
        depth += 1
        kind = "hinge" if joint["type"] == "revolute" else "slide"
        lo, hi = joint["limit"]
        lines.append(_ind(depth, (
            f'<joint name="{joint["name"]}" type="{kind}" axis="{_vec(joint["axis"])}" '
            f'range="{lo:.8f} {hi:.8f}"/>'
        )))
        lines.append(_ind(depth, (
            f'<geom type="sphere" size="0.012" mass="{mass}" rgba="{_rgba(joint["length_identifiable"])}" '
            f'contype="0" conaffinity="0"/>'
        )))
    tip = tree["tip"]
    if tip["length_identifiable"] is False:
        lines.append(_ind(depth, "<!-- non-identifiable length: tip_link -->"))
    lines.append(_ind(depth, f'<body name="tip_link" pos="{_vec(tip["origin_m"])}">'))
    lines.append(_ind(depth + 1, '<site name="tip" pos="0 0 0" size="0.01"/>'))
    lines.append(_ind(depth + 1, (
        f'<geom type="sphere" size="0.015" mass="{mass}" rgba="{_rgba(tip["length_identifiable"], tip=True)}" '
        f'contype="0" conaffinity="0"/>'
    )))
    lines.append(_ind(depth, "</body>"))
    for _ in tree["joints"]:
        depth -= 1
        lines.append(_ind(depth, "</body>"))
    lines.append("</worldbody>")
    lines.append("<custom>")
    for joint in tree["joints"]:
        lines.append(
            f'  <numeric name="{joint["name"]}_metres_per_command" data="{joint["metres_per_command"]:.12f}"/>'
        )
    lines.append("</custom>")
    lines.append("</mujoco>")
    lines.append("")
    return "\n".join(lines)


def render_report(tree: dict) -> str:
    rows = []
    for joint in tree["joints"]:
        rows.append(_row(joint, base=(joint["chain_index"] == 0)))
    tip = tree["tip"]
    rows.append(_row({
        "link": tip["name"], "channel": None, "type": "fixed", "axis": None,
        "origin_m": tip["origin_m"], "length_m": tip["length_m"],
        "metres_per_command": None, "length_identifiable": tip["length_identifiable"],
    }, base=False))
    struct = " ".join(tree.get("structure_channel_order") or [])
    order = " ".join(str(c) for c in tree["chain_order"])
    extra = ""
    if tree.get("shortest_equivalent_differs"):
        extra = (
            "<p>The swarm's reported link lengths are the shortest body with the same training tips. "
            "These files use the parameters predict() evaluates.</p>"
        )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8"/>\n'
        "<title>BodyScout learned body</title>\n<style>\n"
        "body { font: 16px/1.45 'Segoe UI', system-ui, sans-serif; margin: 2rem auto;"
        " max-width: 56rem; color: #1c1c1c; }\n"
        "table { border-collapse: collapse; width: 100%; margin: 1rem 0 1.5rem; }\n"
        "th, td { border-bottom: 1px solid #e2e2e2; text-align: left; padding: 0.4rem 0.45rem;"
        " vertical-align: top; }\n"
        "th { font-size: 0.85rem; }\n"
        ".note { background: #f4f1e8; padding: 0.85rem 1rem; }\n"
        ".mark { color: #8a4b08; font-weight: 600; }\n"
        "code { font-size: 0.92em; }\n"
        "</style>\n</head>\n<body>\n"
        "<h1>Learned body</h1>\n"
        f"{_run_paragraph(tree.get('run') or {})}\n"
        f"<p>Structure in channel order: <code>{escape(struct)}</code>. "
        f"Chain order, base first, is the channel driving each link: <code>{escape(order)}</code>.</p>\n"
        '<p class="note">Masses are a placeholder mass: 0.1 kg, not identified. '
        "A non-identifiable length is an origin the training motions could not pin. "
        "The number in the file is one origin that fits the tips.</p>\n"
        f"{extra}\n"
        "<table>\n<thead><tr>"
        "<th>Link</th><th>Channel</th><th>Joint</th><th>Axis</th>"
        "<th>Origin (mm)</th><th>Length (mm)</th><th>Command</th><th>Length</th>"
        "</tr></thead>\n<tbody>\n"
        + "\n".join(rows) + "\n</tbody>\n</table>\n"
        "<p>Files written next to this page: <code>robot.urdf</code>, <code>robot.xml</code>, "
        "<code>body.json</code>.</p>\n"
        "</body>\n</html>\n"
    )


def _axis_and_gain(angs, slide: bool):
    """Unit axis, and the metres a command of 1 moves a slide.

    A hinge command is already radians, so its gain is 1. ``_fk`` normalises
    the hinge axis. A slide keeps the fitted length: that length is metres per
    command unit.
    """
    angs = np.asarray(angs, float)
    n = float(np.linalg.norm(angs))
    if slide:
        if n < 1e-12:
            return np.array([0.0, 0.0, 1.0]), 0.0
        return angs / n, n
    raw = angs / (n + 1e-9)
    rn = float(np.linalg.norm(raw))
    if rn < 1e-8:  # _fk's Rodrigues of a zero axis does not rotate; z is a stand-in
        return np.array([0.0, 0.0, 1.0]), 1.0
    return raw / rn, 1.0


def _slide_limit(gain: float):
    half = max(1.0, 3.0 * abs(gain))
    return (-half, half)


def _flag(flags, index):
    if flags is None or index < 0 or index >= len(flags):
        return None
    return bool(flags[index])


def _shortest_differs(model, p, offs, tip) -> bool:
    if model.report_params is None:
        return False
    rp = np.asarray(model.report_params, float).reshape(-1)
    if rp.size != p.size:
        return False
    ro, _, rt = model._unpack(rp)
    pairs = [(offs[i], ro[i]) for i in range(1, model.n)] + [(tip, rt)]
    return any(abs(float(np.linalg.norm(a) - np.linalg.norm(b))) > 1e-4 for a, b in pairs)


def _scale_comment(joint: dict) -> str:
    if joint["type"] == "revolute":
        how = "joint position is the command in radians"
    else:
        how = f"joint position in metres = {joint['metres_per_command']:.12f} * command"
    return f"channel {joint['channel']}, {joint['type']}, {how}"


def _joint_xml(lines, joint, parent, child, level):
    lines.append(_ind(level, f"<!-- {_scale_comment(joint)} -->"))
    if joint["length_identifiable"] is False:
        lines.append(_ind(level, f"<!-- non-identifiable length: {child} -->"))
    lines.append(_ind(level, f'<joint name="{joint["name"]}" type="{joint["type"]}">'))
    lo, hi = joint["limit"]
    lines.append(_ind(level + 1, f'<origin xyz="{_vec(joint["origin_m"])}" rpy="0 0 0"/>'))
    lines.append(_ind(level + 1, f'<parent link="{parent}"/>'))
    lines.append(_ind(level + 1, f'<child link="{child}"/>'))
    lines.append(_ind(level + 1, f'<axis xyz="{_vec(joint["axis"])}"/>'))
    lines.append(_ind(level + 1,
                       f'<limit lower="{lo:.8f}" upper="{hi:.8f}" effort="1" velocity="1"/>'))
    lines.append(_ind(level, "</joint>"))


def _fixed_xml(lines, tip, parent, level):
    lines.append(_ind(level, "<!-- fixed tip frame -->"))
    if tip["length_identifiable"] is False:
        lines.append(_ind(level, "<!-- non-identifiable length: tip_link -->"))
    lines.append(_ind(level, '<joint name="tip" type="fixed">'))
    lines.append(_ind(level + 1, f'<origin xyz="{_vec(tip["origin_m"])}" rpy="0 0 0"/>'))
    lines.append(_ind(level + 1, f'<parent link="{parent}"/>'))
    lines.append(_ind(level + 1, '<child link="tip_link"/>'))
    lines.append(_ind(level, "</joint>"))


def _link_xml(lines, name, mass, radius, level):
    lines.append(_ind(level, f'<link name="{name}">'))
    lines.append(_ind(level + 1, "<inertial>"))
    lines.append(_ind(level + 2, '<origin xyz="0 0 0" rpy="0 0 0"/>'))
    lines.append(_ind(level + 2, f'<mass value="{_mass(mass)}"/>'))
    lines.append(_ind(level + 2, '<inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>'))
    lines.append(_ind(level + 1, "</inertial>"))
    lines.append(_ind(level + 1, "<visual>"))
    lines.append(_ind(level + 2, f'<geometry><sphere radius="{radius:.3f}"/></geometry>'))
    lines.append(_ind(level + 1, "</visual>"))
    lines.append(_ind(level, "</link>"))


def _row(item, base: bool) -> str:
    flag = item["length_identifiable"]
    if flag is False:
        status = "non-identifiable length"
    elif flag is True:
        status = "identifiable"
    elif base:
        status = "base offset"
    else:
        status = "not scored"
    status_cell = f'<td class="mark">{status}</td>' if flag is False else f"<td>{status}</td>"
    channel = "—" if item["channel"] is None else str(item["channel"])
    axis = "—" if not item.get("axis") else " ".join(f"{float(x):.4f}" for x in item["axis"])
    if item["type"] == "revolute":
        command = "radians"
    elif item["type"] == "prismatic":
        command = f"{item['metres_per_command'] * 1000:.2f} mm per command"
    else:
        command = "—"
    cells = (
        f"<td>{escape(item['link'])}</td>"
        f"<td>{channel}</td>"
        f"<td>{escape(item['type'])}</td>"
        f"<td>{axis}</td>"
        f"<td>{_mm_vec(item['origin_m'])}</td>"
        f"<td>{item['length_m'] * 1000:.1f}</td>"
        f"<td>{command}</td>"
        f"{status_cell}"
    )
    return f'<tr data-name="{escape(item["link"])}">{cells}</tr>'


def _run_paragraph(run: dict) -> str:
    if not run:
        return ""
    head = "Crowned chain" if run.get("crowned", True) else "Chain model"
    if run.get("robot"):
        head += f" for <code>{escape(str(run['robot']))}</code>"
    details = []
    if "seed" in run:
        details.append(f"seed {int(run['seed'])}")
    if "motions" in run and "budget" in run:
        details.append(f"{int(run['motions'])} motions (budget {int(run['budget'])})")
    elif "motions" in run:
        details.append(f"{int(run['motions'])} motions")
    elif "budget" in run:
        details.append(f"budget {int(run['budget'])}")
    if run.get("unknown_body"):
        details.append("body type unknown")
    sentence = head + (", " + ", ".join(details) if details else "") + "."
    extra = []
    if run.get("holdout_mm") is not None:
        extra.append(f"Holdout {float(run['holdout_mm']):.2f} mm")
    if run.get("votes") is not None:
        extra.append(f"{int(run['votes'])} validator votes")
    if extra:
        sentence += " " + ", ".join(extra) + "."
    return f"<p>{sentence}</p>"


def _mm_vec(v) -> str:
    return " ".join(f"{float(x) * 1000:.1f}" for x in v)


def _rgba(flag, tip=False) -> str:
    if flag is False:
        return "0.75 0.55 0.20 1"
    if tip:
        return "0.90 0.30 0.20 1"
    return "0.30 0.50 0.80 1"


def _mass(mass) -> str:
    return f"{float(mass):.4g}"


def _vec(v) -> str:
    return " ".join(f"{float(x):.12f}" for x in v)


def _r(x) -> float:
    return float(f"{float(x):.12f}")


def _ind(level: int, text: str) -> str:
    return ("  " * level) + text


def _write(path, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, np.ndarray):
        return _jsonable(v.tolist())
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)
