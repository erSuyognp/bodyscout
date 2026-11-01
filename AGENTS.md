# BodyScout: context for Codex

ScienceClaw Hack (MIT Media Lab, Oct 30 to Nov 1 2026). Slides due Sunday 2:30 PM, judging 4 PM.

## What this is
A decentralized swarm of agents that discovers any jointed robot's body from scratch (no model file,
not even its type: arm, gantry, SCARA or telescoping boom),
plans reaches with what it learned, and notices + recovers when the body is damaged.
Judges score: problem 20%, impact 25%, decentralized agency 20%, collective capability 25%
(swarm vs single agent, same budget), execution/validation 10%, +10 for tools other teams reuse.

## The one rule that must never break
Agents (everything in `bodyscout/agents.py`, `models.py`, `planning.solve_ik/plan`, and the baseline agent
classes in `swarm.py`: SingleAgent, SingleProbeAgent, PipelineAgent) may only use
`BlackBoxRobot.move`, `.n_channels`, `.limits`. They must NEVER read `robot.spec`, `robot._model`,
`true_tip`, `skeleton`, or any MJCF. Those exist only for scoring (`planning.reach_errors`) and drawing.
If you add a feature that needs ground truth, it belongs in experiments/ or the scorer, not an agent.

## Layout
- `bodyscout/world.py`      hidden world: procedural arms, gantries, SCARA, telescopes (hinge + slide joints), noise, damage
- `bodyscout/models.py`     competing self models: ChainModel (physics prior), GMMModel (Kitchin 2025), MLPModel
- `bodyscout/blackboard.py` ScienceClaw style artifacts (with parents) + needs with pressure
- `bodyscout/agents.py`     Explorer x2, ChannelAgent x 2N (hinge or slide per channel, swept from the home and the
                            bent pose; a channel is settled only when both agree, else "disputed" and every type
                            is proposed), ReviewAgent (rechecks doubtful channels from a third pose when the
                            champion stays above goal), independent
                            hypothesizers (findings, prior, library, one LLM per key: Codex, Gemini;
                            findings also infers the chain order, since channels may be wired in any order),
                            Modeler x4 (chain x2 with different seeds and restarts;
                            chain also assembles findings itself), Validator x2 voting on the
                            public rule `crown(bb)`, Monitor. No role has a single instance without a fallback.
- `bodyscout/menagerie.py`  real arms (Panda, UR5e, Gen3, vx300s) from MuJoCo Menagerie as BlackBoxRobots, channels
                            shuffled; needs the sparse clone in third_party/ (command in the module docstring)
- `bodyscout/env.py`        loads API keys from .env (gitignored); no keys = no LLM hypothesizers
- Structure tokens: "hz" = hinge about z, "sx" = slide along x. `run(..., unknown_body=True)` turns on channel agents.
- `bodyscout/planning.py`   IK on the champion, extrapolation guard, true reach scorer
- `bodyscout/swarm.py`      run(robot, condition) for swarm / pipeline / single_probe / single / mlp, learning curve
                            output; pipeline = the same parts run in a fixed order by one orchestrator
- `bodyscout/faults.py`     fault injection (`run(..., faults=...)`): wrong_finding, bad_llm, modeler_crash,
                            noisy_channel. Hidden world side: it may read robot.spec to be wrong on purpose
- `bodyscout/export.py`     crowned ChainModel to robot.urdf, robot.xml (MJCF), body.json, report.html
- `bodyscout/cli.py`        `python -m bodyscout learn --robot path.py:Class --budget N` runs the swarm, then exports
- `experiments/`            learning_curve.py, damage.py, extrapolation.py, bodies.py, knockout.py, make_plots.py,
                            sweep.py (faults + noise jobs too), provenance_stats.py (reads saved blackboards)
                            (scripts that use a Pool keep their work under `if __name__ == "__main__":`, Windows needs it)
- `demo.py`                 narrated live run + optional video

## Conventions
- Units: metres and radians in code, millimetres in anything a human reads.
- Every new agent posts artifacts with `parents` so the provenance DAG stays complete.
- Keep comparisons fair: same robots (arm seeds), same motion budget, same scorer, same targets.
- Report honest numbers. If a baseline wins somewhere, keep it in the slides and explain why.
- Run `python -m pytest -q` (tests/) and `python demo.py` before saying something works.
- Runs are deterministic: same seeds give identical output; check with two demo runs and diff before claiming a change is neutral.
  (LLM hypothesizers break this: their answers vary. They are off unless a key is set.)
