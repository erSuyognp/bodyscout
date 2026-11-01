"""No-argument black box for the learn command.

    python -m bodyscout learn --robot examples/arm.py:Arm --budget 64
"""
from bodyscout.world import BlackBoxRobot, random_arm


class Arm(BlackBoxRobot):
    """Hinge arm from seed 3. The swarm sees move, n_channels, and limits."""

    def __init__(self):
        super().__init__(random_arm(3), seed=3)
