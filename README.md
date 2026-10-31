# BodyScout

A swarm of agents that discovers any jointed robot's body from scratch (arm, gantry, SCARA or
telescoping boom, and it is not told which), plans with what it learned, and notices and recovers
when the body is damaged. Built for ScienceClaw Hack, MIT Media Lab, Oct 2026.

Agents only send joint commands and see a noisy fingertip. They never read the robot's model file.
MuJoCo holds the hidden truth, so every claim is scored exactly.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # optional: lets the hypothesizer ask Claude
PYTHONPATH=. python -m pytest -q tests     # 4 tests
python demo.py                             # narrated learn, damage, recover run
python demo.py --video demo.mp4            # backup video (needs ffmpeg)
python demo.py --family scara              # unknown body mode: channel agents find the structure
```

## Experiments (run from the repo root)

```bash
python experiments/learning_curve.py --arms 6   # swarm vs single vs neural net, same budget
python experiments/damage.py --arms 3           # break the arm at motion 48
python experiments/extrapolation.py             # does the planner know when it is guessing?
python experiments/bodies.py --seeds 3          # unknown body types: swarm vs blind single agent
python experiments/make_plots.py                # results/fig_*.png + results/summary.md
```

## Agents

| Agent | Job |
| --- | --- |
| Explorer | Owns the robot channels; picks motions where competing models disagree |
| Channel agent x N | Owns one channel; sweeps only it; a straight tip path = slide, an arc = hinge; posts the axis |
| Hypothesizer | Assembles channel findings into whole body structures (plus Claude, skill library, prior) |
| Modeler x3 | Chain (physics prior), GMM (Kitchin 2025 generative inverse), MLP; refit on new data |
| Validator | Holdout scoring plus replay gate; crowns one champion |
| Monitor | Sentinel motions; declares "my body changed" on repeated surprise and opens a new epoch |
| Planner | IK on the champion; refuses targets the model says are out of reach |

All agents talk only through `Blackboard` (artifacts with parent lineage + needs with pressure).
`runs/*.jsonl` is the full provenance DAG.

## References

- Kitchin, J. R. (2025). Solving an inverse problem with generative models. *Digital Discovery*.
- Zhang et al. (2026). ScienceClaw: continual self evolution of AI for science agents. arXiv 2610.08691.
- Wang, Marom, Pal, Berkovich, Luu, Lu, Buehler (2026). ScienceClaw x Infinite. arXiv 2603.14312.
- Bongard, Zykov, Lipson (2006); Chen, Kwiatkowski, Vondrick, Lipson (2022): robots that model themselves.
