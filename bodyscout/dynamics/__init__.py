"""Dynamics experiments on top of MuJoCo MJX (jax). Optional: needs requirements-dynamics.txt.

Same black box rule as the rest of the swarm: any agent-facing code in here may only use
BlackBoxRobot.move / .n_channels / .limits. Ground truth MJCF is for scoring and tests only.
"""
