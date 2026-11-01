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

## Full sweep on a cloud VM

`experiments/sweep.py` runs every experiment at full scale (418 jobs: bodies 4 families x 10 seeds,
damage 6 kinds x 4 families x 5 robots, learning curve on 10 arms, extrapolation on 4 x 5 robots,
4 Menagerie arms x 3 seeds) in one pool across all cores. It is too big for a laptop, so run it on a
32 to 64 vCPU machine. Each finished job is one line in `results/sweep.jsonl`. If the run dies,
start the same command again: finished jobs are skipped. The log prints an ETA after every job.
LLM hypothesizers stay off, so you need no API key on the VM.

### Brev (primary)

Create a CPU instance with 32 to 64 vCPUs and Ubuntu in the Brev console (no GPU needed), then:

```bash
brev shell bodyscout-sweep          # or SSH in with the command the console shows
```

On the instance:

```bash
sudo apt-get update && sudo apt-get install -y git tmux python3-venv
git clone https://github.com/erSuyognp/bodyscout.git && cd bodyscout
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
git clone --depth 1 --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie.git third_party/mujoco_menagerie
git -C third_party/mujoco_menagerie sparse-checkout set franka_emika_panda universal_robots_ur5e kinova_gen3 trossen_vx300s
python experiments/sweep.py --dry-run          # job count, nothing runs
tmux new -s sweep "source .venv/bin/activate && python experiments/sweep.py 2>&1 | tee -a results/sweep.log"
```

Detach with `Ctrl-b d`, come back with `tmux attach -t sweep`, and check progress with
`tail -f results/sweep.log`. After a disconnect or reboot, run the same `tmux new ...` line again.
Copy the results to your laptop (run this on the laptop; `brev ls` shows the instance name):

```bash
scp bodyscout-sweep:bodyscout/results/sweep.jsonl results/
```

Stop the instance in the Brev console when you are done.

### Google Cloud (backup)

```bash
gcloud compute instances create bodyscout-sweep --zone=us-central1-a --machine-type=c2d-standard-32 \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud --boot-disk-size=30GB
gcloud compute ssh bodyscout-sweep --zone=us-central1-a
```

On the VM, run the same commands as the Brev block above (from `sudo apt-get` to `tmux new`).
Then, on the laptop:

```bash
gcloud compute scp bodyscout-sweep:~/bodyscout/results/sweep.jsonl results/ --zone=us-central1-a
gcloud compute instances delete bodyscout-sweep --zone=us-central1-a   # stops the billing
```

If `c2d-standard-32` is out of quota in that zone, `n2-standard-32` or another zone works too.
Spot VMs (`--provisioning-model=SPOT`) are cheaper and safe here, because the sweep resumes.

## Dashboard

`dashboard/index.html` is one self contained page (no build step, no libraries). It reads
`runs/demo_blackboard.jsonl`, `runs/demo_summary.json`, `results/bodies.csv`,
`results/bodies_meta.json` and `results/learning.csv`, and shows the provenance DAG as an animated
timeline (one lane per agent, needs as dashed arrows, the hidden damage as a red line), the
unknown body types result, reach error vs motions, and the champion's structure with a truth reveal.
`runs/` is gitignored, so make the demo run first:

```bash
python demo.py --unknown                  # channel agents on, writes runs/demo_*.json(l)
python -m http.server 8000                # from the repo root, then open http://localhost:8000/dashboard/
```

Another run: `/dashboard/?bb=../runs/other.jsonl&summary=../runs/other_summary.json`.

A pick-and-place trial puts the swarm and the task planner on one blackboard. The arm is damaged after the first reach. The log shows the plan, the monitor alarm, the re-plan, the next champion, grasp and ungrasp, and whether the cube was placed.

```bash
python experiments/task.py --demo --damage long_link
python -m http.server 8000
```

Open `http://localhost:8000/dashboard/?bb=../runs/task_blackboard.jsonl&summary=../runs/task_summary.json`.
Needs are dashed arrows labelled with pressure. The crowned champion, the red damage line, the re-plan and the recovery plan, and a placed or missed marker are on the timeline.

### Cloud Run

The `Dockerfile` serves the page and its data (nothing else; `.env` never enters the image) with
nginx on `$PORT`. Cloud Run gives it an HTTPS URL, so no VM and no firewall rule is involved.

```bash
gcloud run deploy bodyscout-dashboard --source . --region us-central1 --allow-unauthenticated
```

`--source .` builds the Dockerfile with Cloud Build; `.gcloudignore` keeps `runs/` in the upload
and `.env`, `.git`, `third_party` out. Drop `--allow-unauthenticated` to keep it private
(viewers then need `roles/run.invoker`). Local check: `docker build -t bodyscout-dash . &&
docker run --rm -p 127.0.0.1:8080:8080 bodyscout-dash`.

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
