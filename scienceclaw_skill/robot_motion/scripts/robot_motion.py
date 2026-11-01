#!/usr/bin/env python3
"""robot_motion: command a black box jointed robot and observe its tip (BodyScout skill)."""
import os
import sys
from pathlib import Path

here = Path(__file__).resolve().parent.parent
pinned = here / "bodyscout_root.txt"  # written by scienceclaw_bridge.install_skill
root = os.environ.get("BODYSCOUT_ROOT") or (pinned.read_text().strip() if pinned.exists() else str(here.parent.parent))
sys.path.insert(0, root)

from bodyscout.scienceclaw_bridge import robot_motion_cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(robot_motion_cli())
