"""Exported MJCF, loaded back, matches ChainModel.predict within 1 mm."""
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from bodyscout.cli import load_robot, main
from bodyscout.export import export_chain
from bodyscout.models import ChainModel


def _body(path):
    return json.loads((Path(path) / "body.json").read_text(encoding="utf-8"))


def _roundtrip(model, path, body, qs):
    mj = mujoco.MjModel.from_xml_path(str(Path(path) / "robot.xml"))
    data = mujoco.MjData(mj)
    tip_id = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_SITE, "tip")
    assert tip_id >= 0
    assert mj.nq == len(body["joints"])
    for joint in body["joints"]:
        jid = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_JOINT, joint["name"])
        assert jid >= 0
        kind = mujoco.mjtJoint.mjJNT_HINGE if joint["type"] == "revolute" else mujoco.mjtJoint.mjJNT_SLIDE
        assert mj.jnt_type[jid] == kind
        bid = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_BODY, joint["link"])
        assert np.allclose(mj.body_pos[bid], joint["origin_m"], atol=1e-8)
        assert mj.body_mass[bid] == pytest.approx(0.1, abs=1e-6)
        want = np.array(joint["axis"], float)
        want /= np.linalg.norm(want)
        assert np.allclose(mj.jnt_axis[jid], want, atol=1e-6)
        if joint["type"] == "revolute":
            assert mj.jnt_range[jid, 1] == pytest.approx(np.pi, abs=1e-4)
        nid = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_NUMERIC, joint["name"] + "_metres_per_command")
        assert nid >= 0
        gain = float(mj.numeric_data[int(mj.numeric_adr[nid])])
        assert gain == pytest.approx(joint["metres_per_command"], abs=1e-9)
    tip_body = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_BODY, "tip_link")
    assert np.allclose(mj.body_pos[tip_body], body["tip"]["origin_m"], atol=1e-8)
    assert mj.body_mass[tip_body] == pytest.approx(0.1, abs=1e-6)

    worst, worst_q = 0.0, None
    for q in qs:
        data.qpos[:] = 0.0
        for joint in body["joints"]:
            jid = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_JOINT, joint["name"])
            adr = int(mj.jnt_qposadr[jid])
            data.qpos[adr] = joint["metres_per_command"] * float(np.asarray(q, float)[joint["channel"]])
        mujoco.mj_kinematics(mj, data)
        err = float(np.linalg.norm(data.site_xpos[tip_id] - model.predict(np.asarray(q, float)[None])[0]))
        if err > worst:
            worst, worst_q = err, np.asarray(q, float).copy()
    assert worst < 0.001, (worst, worst_q)


def _hand_model():
    m = ChainModel(4, seed=0)
    m.types = ["h", "s", "h", "h"]
    m.order = [1, 3, 0, 2]
    offs = np.array([
        [0.01, -0.02, 0.08],
        [0.15, 0.02, 0.0],
        [0.0, 0.0, 0.11],
        [0.04, -0.03, 0.07],
    ])
    angs = np.array([
        [0.0, 0.0, 1.0],
        [0.0, -0.04, 0.03],   # slide, length is metres per command
        [0.2, 0.9, -0.1],
        [1.0, 0.0, 0.3],
    ])
    tip = np.array([0.02, 0.09, 0.04])
    m.params = np.concatenate([offs.ravel(), angs.ravel(), tip])
    m.report_params = m.params.copy()
    m.identifiable = [True, False, True, False]  # offs[1], offs[2], offs[3], tip
    return m


def test_export_mjcf_roundtrip_marks_unidentifiable_lengths(tmp_path):
    model = _hand_model()
    export_chain(model, tmp_path, meta={"robot": "arm.py:Arm", "budget": 4, "seed": 0,
                                        "motions": 4, "crowned": True})
    for name in ("robot.urdf", "robot.xml", "body.json", "report.html"):
        assert (tmp_path / name).is_file()
    body = _body(tmp_path)
    assert [j["channel"] for j in body["joints"]] == [1, 3, 0, 2]
    assert body["masses"] == "placeholder" and body["placeholder_mass_kg"] == 0.1
    assert [j["length_identifiable"] for j in body["joints"]] == [None, True, False, True]
    assert body["tip"]["length_identifiable"] is False
    _, angs, _ = model._unpack(model.params)
    assert body["joints"][0]["metres_per_command"] == 1.0
    assert body["joints"][1]["metres_per_command"] == pytest.approx(np.linalg.norm(angs[1]), abs=1e-9)
    assert body["joints"][1]["type"] == "prismatic"
    offs, _, tip = model._unpack(model.params)
    for i, joint in enumerate(body["joints"]):
        assert np.allclose(joint["origin_m"], offs[i], atol=1e-9)
    assert np.allclose(body["tip"]["origin_m"], tip, atol=1e-9)

    urdf = (tmp_path / "robot.urdf").read_text(encoding="utf-8")
    xml = (tmp_path / "robot.xml").read_text(encoding="utf-8")
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    for text in (urdf, xml):
        assert 'type="revolute"' in text or 'type="hinge"' in text
        assert 'type="prismatic"' in text or 'type="slide"' in text
        assert "placeholder mass" in text
        assert "non-identifiable length: link2_c0" in text
        assert "non-identifiable length: tip_link" in text
        assert "non-identifiable length: link0_c1" not in text
        assert "non-identifiable length: link1_c3" not in text
        assert "non-identifiable length: link3_c2" not in text
    assert 'value="0.1"' in urdf and 'type="fixed"' in urdf
    assert "shortest body with the same training tips" not in html
    for line in html.splitlines():
        if 'data-name="link2_c0"' in line or 'data-name="tip_link"' in line:
            assert "non-identifiable length" in line
        if 'data-name="link1_c3"' in line or 'data-name="link3_c2"' in line:
            assert "non-identifiable" not in line
    assert "150.0" in html  # 0.15 m link, millimetres for a person

    rng = np.random.default_rng(0)
    qs = [np.zeros(4), np.array([0.0, 0.4, 0.0, 0.0]), np.array([0.0, 0.0, 0.0, -1.1])]
    qs += list(rng.uniform(-1.5, 1.5, (12, 4)))
    _roundtrip(model, tmp_path, body, qs)


def test_export_uses_predict_parameters(tmp_path):
    from bodyscout.world import BlackBoxRobot, random_arm

    spec = random_arm(1, n_joints=3)
    robot = BlackBoxRobot(spec, obs_noise=0.0, backlash=0.0, settle_steps=20, seed=0)
    rng = np.random.default_rng(0)
    commands = rng.uniform(-1.2, 1.2, (24, robot.n_channels))
    tips = np.array([robot.true_tip(q) for q in commands])
    model = ChainModel(robot.n_channels, restarts=1, seed=0).fit(commands, tips, patterns=[spec.tokens()])
    model.report_params = model.params.copy()
    model.report_params[3:6] += 0.25
    export_chain(model, tmp_path)
    body = _body(tmp_path)
    offs, _, tip = model._unpack(model.params)
    for i, joint in enumerate(body["joints"]):
        assert np.allclose(joint["origin_m"], offs[i], atol=1e-9)
    assert np.allclose(body["tip"]["origin_m"], tip, atol=1e-9)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "shortest body with the same training tips" in html
    rng = np.random.default_rng(1)
    qs = [np.zeros(robot.n_channels)] + list(rng.uniform(-1.2, 1.2, (8, robot.n_channels)))
    _roundtrip(model, tmp_path, body, qs)


def test_export_requires_a_fit(tmp_path):
    with pytest.raises(ValueError):
        export_chain(ChainModel(2), tmp_path)


def test_export_refuses_a_branched_fit(tmp_path):
    model = _hand_model()
    model.tree = True
    with pytest.raises(ValueError, match="serial chain"):
        export_chain(model, tmp_path)


def test_load_robot_on_a_windows_path(tmp_path):
    path = tmp_path / "arm.py"
    path.write_text(
        "class Arm:\n"
        "    def __init__(self):\n"
        "        self.n_channels = 2\n"
        "        self.limits = (-2.0, 2.0)\n"
        "        self.motions = 0\n"
        "    def move(self, q):\n"
        "        self.motions += 1\n"
        "        return [0.0, 0.0, 0.0]\n"
        "    def true_tip(self, q):\n"
        "        return [0.0, 0.0, 0.0]\n",
        encoding="utf-8",
    )
    robot = load_robot(f"{path}:Arm")
    assert robot.n_channels == 2 and robot.limits == (-2.0, 2.0)
    bare = tmp_path / "bare.py"
    bare.write_text("class Arm:\n    n_channels = 1\n    limits = (-1, 1)\n    def move(self, q):\n        return q\n",
                    encoding="utf-8")
    with pytest.raises(SystemExit, match="true_tip"):
        load_robot(f"{bare}:Arm")


def test_learn_requires_robot_and_budget():
    with pytest.raises(SystemExit):
        main(["learn", "--budget", "4"])
    with pytest.raises(SystemExit, match="not found"):
        main(["learn", "--robot", "no_such_robot.py:Arm", "--budget", "4"])


def test_example_arm_loads():
    root = Path(__file__).resolve().parents[1]
    robot = load_robot(f"{root / 'examples' / 'arm.py'}:Arm")
    assert robot.n_channels >= 3
    assert robot.limits[0] < robot.limits[1]
