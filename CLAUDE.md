# BodyScout: context for Claude Code

ScienceClaw Hack (MIT Media Lab, Oct 30 to Nov 1 2026). Slides due Sunday 2:30 PM, judging 4 PM.

## What this is
A decentralized swarm of agents that discovers any jointed robot's body from scratch (no model file,
not even its type: arm, gantry, SCARA or telescoping boom),
plans reaches with what it learned, and notices + recovers when the body is damaged.
Judges score: problem 20%, impact 25%, decentralized agency 20%, collective capability 25%
(swarm vs single agent, same budget), execution/validation 10%, +10 for tools other teams reuse.

## The one rule that must never break
Agents (everything in `bodyscout/agents.py`, `models.py`, `planning.solve_ik/plan`) may only use
`BlackBoxRobot.move`, `.n_channels`, `.limits`. They must NEVER read `robot.spec`, `robot._model`,
`true_tip`, `skeleton`, or any MJCF. Those exist only for scoring (`planning.reach_errors`) and drawing.
If you add a feature that needs ground truth, it belongs in experiments/ or the scorer, not an agent.

## Layout
- `bodyscout/world.py`      hidden world: procedural arms, gantries, SCARA, telescopes (hinge + slide joints), noise, damage
- `bodyscout/models.py`     competing self models: ChainModel (physics prior), GMMModel (Kitchin 2025), MLPModel
- `bodyscout/blackboard.py` ScienceClaw style artifacts (with parents) + needs with pressure
- `bodyscout/agents.py`     Explorer, ChannelAgent x N (hinge or slide per channel), Hypothesizer (Claude),
                            Modeler x3, Validator (holdout + replay gate), Monitor
- Structure tokens: "hz" = hinge about z, "sx" = slide along x. `run(..., unknown_body=True)` turns on channel agents.
- `bodyscout/planning.py`   IK on the champion, extrapolation guard, true reach scorer
- `bodyscout/swarm.py`      run(robot, condition) for swarm / single / mlp, learning curve output
- `experiments/`            learning_curve.py, damage.py, extrapolation.py, make_plots.py
- `demo.py`                 narrated live run + optional video

## Conventions
- Units: metres and radians in code, millimetres in anything a human reads.
- Every new agent posts artifacts with `parents` so the provenance DAG stays complete.
- Keep comparisons fair: same robots (arm seeds), same motion budget, same scorer, same targets.
- Report honest numbers. If a baseline wins somewhere, keep it in the slides and explain why.
- Run `python -m pytest -q` (tests/) and `python demo.py` before saying something works.
- Runs are deterministic: same seeds give identical output; check with two demo runs and diff before claiming a change is neutral.
