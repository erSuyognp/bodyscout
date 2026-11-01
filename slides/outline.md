# BodyScout: slide outline

Eight slides, one claim each. Every number comes from `results/slide_numbers.md` (tag `results-final`) with its n;
section references (§) point into `results/summary.md`. Reach error is the median miss on held-out reachable targets,
with the bootstrap 95% CI of the median in brackets. "Independent seeds" are 101 to 105.

---

## Slide 1. The mystery

**Claim: here is a robot with unlabeled command channels and no model file. Nobody tells us what it is.**

- Channels in, a noisy fingertip position out. No URDF, no MJCF, not even its type: arm, gantry, SCARA or telescoping boom.
- The channels may be wired in any order, and a part may lie or break while we watch.
- Question for the room: what is it, and can you make it reach a point?

Figure: none. Show the black box: a row of unlabeled channel sliders and a dot that moves.

---

## Slide 2. The swarm figures it out

**Claim: told nothing about the body, the swarm recovers every joint's type and axis.**

- Channel agents sweep one channel at a time, two agents per channel from different poses; a channel is settled only when they agree, otherwise every type is proposed. The swarm spends 36 [32 to 40] of its 64 motions on these sweeps (n = 60). (§10)
- Independent hypothesizers turn findings into structures; modelers fit them; two validators crown a structure by held-out error.
- Reveal: the full structure is right on **20/20** robots on the independent seeds and 40/40 on the original seeds (n = 60). A single agent searching blind gets 5/20 and 6/40. (§1)
- But single_probe and the pipeline, which probe channels the same way, also get 20/20 on the independent seeds (n = 20 each; §1 row "all", `fig_bodies.png`). So the reveal shows that probing works; whether the swarm is needed is the question slide 5 tests.
- Unknown body score: reach error **1.5 [1.4 to 1.9] mm** after 64 motions, n = 20 (independent); 1.6 [1.3 to 2.0] mm, n = 40 (original). (§1)
- Every final champion (no fault, n = 40) descends from 7 (6 to 8) distinct agent types; in 39 of 40, two or more sources had proposed structures that disagreed. (§11)

Figure: `results/fig_bodies.png`

---

## Slide 3. Secret damage

**Claim: break the robot mid run and the swarm notices, pauses and relearns, and the task survives where a single agent's fails.**

- Alarm: the swarm noticed the damage in **97/120** runs (81%); 20/20 for locked joint, long link, reversed motor and tool, 16/20 for bent axis, 1/20 for payload. (§3)
- It takes a median 26 to 32 motions after the damage for those five kinds (n = 16 to 20 detected runs per kind). (§3)
- Pause: between the alarm and the next crowned model the planner refuses to move.
- Cube pick and place, damage (long link) at motion 48, n = 20 arms: swarm **20/20 before and 20/20 after** (2.9 [2.3 to 3.7] then 4.7 [2.4 to 6.5] mm, a replan requested in all 20); single agent 20/20 before, **4/20 after** (149.1 [54.9 to 376.0] mm). (§4)
- Caveat on the slide: 64 motions after the damage the swarm has a trusted model in only **59/120** runs (pipeline 112/120, single agents 120/120). (§3)
- The pipeline (same parts, fixed order) detects **95/120** (swarm 97/120) and has a trusted model at motion 128 in **112/120** vs the swarm's 59/120. So damage handling comes from the monitor and validator parts, not from the collective; the win on this slide is over the single agent, in the cube task. (§3)

Figure: `results/fig_damage.png`

---

## Slide 4. It holds up at scale

**Claim: one system for four body families, real arms, six damage kinds and four noise levels.**

- 1938 sweep jobs, 0 left to run (240 bodies, 480 damage, 800 faults, 320 noise, 48 real arm, 30 learning, 20 extrapolation). (header)
- Bodies: 20/20 structures right, 1.5 [1.4 to 1.9] mm, n = 20 independent seeds. (§1)
- Real arms (Panda, UR5e, Gen3, vx300s, channels in order and shuffled; n = 3 seeds per setting): every observable joint right in all 8 settings, reach 1.9 to 2.6 mm vs the single agent's 270 to 592 mm. (§2)
- Damage: detected on 97/120 runs across six kinds. (§3)
- Noise: at 10 mm camera noise the swarm ends at **9.1 [6.4 to 21.2] mm** vs single 50.0, single_probe 43.1, pipeline 31.0 mm (n = 20 each); zero false alarms at any noise level (0/20 each). (§6)
- It knows when it is guessing: refuses 200/200 out-of-reach targets and 0/200 reachable ones; without the guard a planner misses by 466 [452 to 517] mm. (§8)

Figures: `results/fig_noise.png`, `results/fig_extrapolation.png` (and `fig_bodies.png` from slide 2)

---

## Slide 5. Is the swarm necessary?

**Claim: only the collective stays under 10 mm on all four faults: swarm 4/4, single_probe 3/4, pipeline 1/4, single 0/4 (independent seeds).**

Same 64 motion budget, same robots, same scorer; a fault counts when the median reach error at 64 motions is under 10 mm, and a run that ends with no model counts as a miss (`fig_faults.png`, from §5 independent seeds).

- single_probe has no LLM stage, so bad_llm cannot affect it; its 3/4 includes that fault. Of the three faults that can reach it, it stays under 10 mm on modeler_crash (3.2 mm) and noisy_channel (3.7 mm) and fails on wrong_finding (43.8 mm). (§5)
- Under noisy_channel the swarm is under 10 mm (5.1 mm) but single_probe and the pipeline end closer (3.7 mm); see slide 6. (§5)
- Clean body (independent seeds, n = 20): single_probe 1.3 [1.0 to 1.7] mm and the pipeline 1.7 [1.0 to 2.0] mm **tie** the swarm's 1.5 [1.4 to 1.9] mm. (§5, §1, Ties)
- One channel agent reports a wrong joint type: swarm **1.5 [1.4 to 2.0] mm, 20/20** structures; single_probe 43.8 mm (1/20); pipeline 41.4 mm (3/20). (§5)
- A confident wrong hypothesis source: swarm **1.6 [1.3 to 1.9] mm, 20/20**; pipeline 27.4 mm, 0/20, because its LLM stage has the final say. (§5)
- One chain modeler crashes at motion 24: swarm **1.7 [1.4 to 2.2] mm, 20/20**; the pipeline has no model in 18/20; single_probe 3.2 mm. (§5)
- Knockout: remove any one agent type at motion 24 (11 cases) and the structure is still right on 20/20. (§7)
- Said on the slide: the replication fixes were designed after we saw the fault preview on seeds 1 and 2; they are judged on new seeds 101 to 105, and every number above is from those.

Figure: `results/fig_faults.png`

---

## Slide 6. Failures we found

**Claim: the swarm is not free and not always best; here is every place it loses.**

- A sensor that is wrong every time (20 mm noise on every sweep of one channel): swarm 5.1 mm, structure 13/20; single_probe and the pipeline 3.7 mm (independent seeds). (§5)
- Slow relearning after damage: a trusted model at motion 128 in 59/120 runs vs the pipeline's 112/120. (§3)
- Payload damage is noticed in 1/20 runs. (§3)
- Known arms, nothing to discover: the single agent wins at every checkpoint, 1.5 [1.0 to 2.3] vs 2.4 [1.6 to 3.4] mm at 64 motions, n = 10. (§9)
- Clean bodies: single_probe and the pipeline tie the swarm (slide 5).
- Cost: **91.5 [73.3 to 104.6] agent CPU seconds per robot** for the swarm vs 5.8 (pipeline) to 9.4 (single_probe), n = 60. (§10)
- One validator replay crashed a whole run once (a scipy SVD failure); fixed so a failed replay fails the check. ("Jobs that errored")
- The full table has 102 rows (per family and per seed set); all are in the backup below and in `results/summary.md`, "Failures we found".

Figure: `results/fig_learning.png`; backup: the full Failures table.

---

## Slide 7. How it works, simply

**Claim: independent agents on one evidence board; new abilities are new agents, not a redesign.**

- One blackboard of immutable artifacts with parents, plus open needs with pressure. No agent calls another.
- Explorers serve needs with motions; 2 channel agents per channel and a review agent probe; hypothesizers propose (findings, prior, library, one LLM per key); 4 modelers fit (2 chain, GMM, MLP); 2 validators vote on a public crowning rule; a monitor watches for surprise.
- Every champion traces back to raw motions: 7 (6 to 8) agent types in its ancestry (n = 40). (§11)
- Pravesh added the dynamics and vision agents onto the same board without redesigning anything: two cameras instead of a marker reach 3.0 to 4.3 mm median triangulation error per family. (§13; dynamics in §12 is from the swarm before the v2 fixes.)
- The review agent and the monitor are single instances; knocking out the review agent still leaves 20/20 structures right. (§7)

Figure: none; draw the board with agents around it (provenance DAG from `results/provenance/` as a backup).

---

## Slide 8. What is next

**Claim: the same board, pointed at real hardware and real labs.**

- Real servos: run the swarm on a physical arm, and fix the two weak spots first: relearning after damage (59/120 runs with a trusted model at motion 128) and a sensor that is always wrong (noisy_channel). (§3, §5)
- Hanging humanoids: many limbs, channels in any order; the same channel agents and hypothesizers, more of them.
- The ScienceClaw skill and the Infinite post: package BodyScout so other teams' agents can call it, and post the run as a shareable artifact.
- Self driving labs: the same loop (probe, propose, validate, notice when the world changes) for any instrument nobody has described.
- Cut the cost: 91.5 s of agent CPU per robot vs 5.8 s for the pipeline. (§10)

Figure: none.

---

## Slide 6 backup: every row of "Failures we found"

Copied verbatim from `results/summary.md` (tag `results-final`). Numbers are reach error in mm, median [95% CI] n.

| experiment | setting | what happened | numbers |
| --- | --- | --- | --- |
| bodies, original seeds 1 to 10 | arm | single_probe beats the swarm | 2.1 [1.4 to 2.6] n=10 vs swarm 2.1 [1.6 to 2.8] n=10; intervals overlap |
| bodies, original seeds 1 to 10 | arm | pipeline beats the swarm | 2.1 [1.7 to 3.0] n=10 vs swarm 2.1 [1.6 to 2.8] n=10; intervals overlap |
| bodies, original seeds 1 to 10 | gantry | single_probe beats the swarm | 0.9 [0.8 to 1.1] n=10 vs swarm 1.8 [1.2 to 2.4] n=10; intervals do not overlap |
| bodies, original seeds 1 to 10 | gantry | pipeline beats the swarm | 1.2 [1.1 to 1.5] n=10 vs swarm 1.8 [1.2 to 2.4] n=10; intervals overlap |
| bodies, original seeds 1 to 10 | scara | single_probe beats the swarm | 1.3 [1.1 to 1.6] n=10 vs swarm 1.4 [1.1 to 1.6] n=10; intervals overlap |
| bodies, original seeds 1 to 10 | telescope | single_probe beats the swarm | 1.6 [1.3 to 1.8] n=10 vs swarm 1.7 [1.2 to 2.1] n=10; intervals overlap |
| bodies, original seeds 1 to 10 | all | single_probe beats the swarm | 1.4 [1.2 to 1.6] n=40 vs swarm 1.6 [1.3 to 2.0] n=40; intervals overlap |
| bodies, original seeds 1 to 10 | all | pipeline beats the swarm | 1.6 [1.4 to 1.9] n=40 vs swarm 1.6 [1.3 to 2.0] n=40; intervals overlap |
| bodies, independent seeds 101 to 105 | arm | single_probe beats the swarm | 1.6 [1.0 to 2.2] n=5 vs swarm 1.8 [0.8 to 2.8] n=5; intervals overlap |
| bodies, independent seeds 101 to 105 | gantry | single_probe beats the swarm | 0.9 [0.7 to 1.0] n=5 vs swarm 1.3 [0.9 to 1.5] n=5; intervals overlap |
| bodies, independent seeds 101 to 105 | gantry | pipeline beats the swarm | 1.0 [0.8 to 1.3] n=5 vs swarm 1.3 [0.9 to 1.5] n=5; intervals overlap |
| bodies, independent seeds 101 to 105 | scara | single_probe beats the swarm | 1.2 [0.7 to 2.6] n=5 vs swarm 1.8 [0.9 to 2.0] n=5; intervals overlap |
| bodies, independent seeds 101 to 105 | telescope | single_probe beats the swarm | 1.6 [1.4 to 2.2] n=5 vs swarm 1.6 [1.4 to 2.3] n=5; intervals overlap |
| bodies, independent seeds 101 to 105 | all | single_probe beats the swarm | 1.3 [1.0 to 1.7] n=20 vs swarm 1.5 [1.4 to 1.9] n=20; intervals overlap |
| damage | bent_axis | swarm did not notice the damage | 4/20 runs |
| damage | bent_axis | swarm ends with no trusted model in some runs | 10/20 runs; the swarm median covers only the rest |
| damage | locked_joint | swarm ends with no trusted model in some runs | 12/20 runs; the swarm median covers only the rest |
| damage | long_link | swarm ends with no trusted model in some runs | 13/20 runs; the swarm median covers only the rest |
| damage | payload | swarm did not notice the damage | 19/20 runs |
| damage | payload | single_probe beats the swarm | 1.6 [1.2 to 2.7] n=20 vs swarm 2.3 [1.6 to 2.7] n=20, 1 no model; intervals overlap |
| damage | payload | pipeline beats the swarm | 2.0 [1.7 to 3.2] n=20 vs swarm 2.3 [1.6 to 2.7] n=20, 1 no model; intervals overlap |
| damage | payload | swarm ends with no trusted model in some runs | 1/20 runs; the swarm median covers only the rest |
| damage | reversed_motor | swarm ends with no trusted model in some runs | 13/20 runs; the swarm median covers only the rest |
| damage | tool | swarm ends with no trusted model in some runs | 12/20 runs; the swarm median covers only the rest |
| faults, original seeds 1 to 5 | none | single_probe beats the swarm | 1.5 [1.2 to 1.7] n=20 vs swarm 1.7 [1.3 to 2.0] n=20; intervals overlap |
| faults, original seeds 1 to 5 | none, arm | pipeline beats the swarm | 2.1 [1.6 to 3.7] n=5 vs swarm 2.1 [1.6 to 3.1] n=5; intervals overlap |
| faults, original seeds 1 to 5 | none, gantry | single_probe beats the swarm | 0.9 [0.9 to 1.6] n=5 vs swarm 1.9 [1.2 to 2.6] n=5; intervals overlap |
| faults, original seeds 1 to 5 | none, gantry | pipeline beats the swarm | 1.2 [1.1 to 2.3] n=5 vs swarm 1.9 [1.2 to 2.6] n=5; intervals overlap |
| faults, original seeds 1 to 5 | bad_llm, gantry | single_probe beats the swarm | 0.9 [0.9 to 1.6] n=5 vs swarm 1.5 [1.3 to 2.6] n=5; intervals overlap |
| faults, original seeds 1 to 5 | noisy_channel | single_probe beats the swarm | 3.0 [2.3 to 3.4] n=20 vs swarm 5.5 [4.3 to 9.3] n=20; intervals do not overlap |
| faults, original seeds 1 to 5 | noisy_channel | pipeline beats the swarm | 3.2 [2.5 to 5.1] n=20 vs swarm 5.5 [4.3 to 9.3] n=20; intervals overlap |
| faults, original seeds 1 to 5 | noisy_channel | swarm structure wrong | 5/20 runs |
| faults, original seeds 1 to 5 | noisy_channel, arm | single_probe beats the swarm | 2.7 [1.8 to 3.5] n=5 vs swarm 5.8 [4.9 to 9.8] n=5; intervals do not overlap |
| faults, original seeds 1 to 5 | noisy_channel, arm | pipeline beats the swarm | 4.0 [2.4 to 5.9] n=5 vs swarm 5.8 [4.9 to 9.8] n=5; intervals overlap |
| faults, original seeds 1 to 5 | noisy_channel, gantry | swarm structure wrong | 3/5 runs |
| faults, original seeds 1 to 5 | noisy_channel, gantry | swarm median over 10 mm | 22.3 [3.9 to 29.2] n=5 |
| faults, original seeds 1 to 5 | noisy_channel, scara | single_probe beats the swarm | 3.0 [1.2 to 35.3] n=5 vs swarm 4.2 [2.9 to 44.2] n=5; intervals overlap |
| faults, original seeds 1 to 5 | noisy_channel, scara | pipeline beats the swarm | 3.0 [2.2 to 29.5] n=5 vs swarm 4.2 [2.9 to 44.2] n=5; intervals overlap |
| faults, original seeds 1 to 5 | noisy_channel, scara | swarm structure wrong | 1/5 runs |
| faults, original seeds 1 to 5 | noisy_channel, telescope | single_probe beats the swarm | 3.2 [2.2 to 31.5] n=5 vs swarm 6.8 [3.9 to 14.4] n=5; intervals overlap |
| faults, original seeds 1 to 5 | noisy_channel, telescope | pipeline beats the swarm | 2.6 [2.1 to 43.5] n=5 vs swarm 6.8 [3.9 to 14.4] n=5; intervals overlap |
| faults, original seeds 1 to 5 | noisy_channel, telescope | swarm structure wrong | 1/5 runs |
| faults, independent seeds 101 to 105 | none | single_probe beats the swarm | 1.3 [1.0 to 1.7] n=20 vs swarm 1.5 [1.4 to 1.9] n=20; intervals overlap |
| faults, independent seeds 101 to 105 | none, arm | single_probe beats the swarm | 1.6 [1.0 to 2.2] n=5 vs swarm 1.8 [0.8 to 2.8] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | none, gantry | single_probe beats the swarm | 0.9 [0.7 to 1.0] n=5 vs swarm 1.3 [0.9 to 1.5] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | none, gantry | pipeline beats the swarm | 1.0 [0.8 to 1.3] n=5 vs swarm 1.3 [0.9 to 1.5] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | none, scara | single_probe beats the swarm | 1.2 [0.7 to 2.6] n=5 vs swarm 1.8 [0.9 to 2.0] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | none, telescope | single_probe beats the swarm | 1.6 [1.4 to 2.2] n=5 vs swarm 1.6 [1.4 to 2.3] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | bad_llm | single_probe beats the swarm | 1.3 [1.0 to 1.7] n=20 vs swarm 1.6 [1.3 to 1.9] n=20; intervals overlap |
| faults, independent seeds 101 to 105 | bad_llm, arm | single_probe beats the swarm | 1.6 [1.0 to 2.2] n=5 vs swarm 2.2 [0.9 to 2.6] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | bad_llm, gantry | single_probe beats the swarm | 0.9 [0.7 to 1.0] n=5 vs swarm 1.2 [0.7 to 1.6] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | bad_llm, scara | single_probe beats the swarm | 1.2 [0.7 to 2.6] n=5 vs swarm 1.8 [1.5 to 2.6] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | bad_llm, telescope | single_probe beats the swarm | 1.6 [1.4 to 2.2] n=5 vs swarm 1.7 [1.4 to 2.9] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | noisy_channel | single_probe beats the swarm | 3.7 [2.5 to 31.2] n=20 vs swarm 5.1 [4.4 to 18.6] n=20, 1 no model; intervals overlap |
| faults, independent seeds 101 to 105 | noisy_channel | pipeline beats the swarm | 3.7 [3.0 to 11.0] n=20 vs swarm 5.1 [4.4 to 18.6] n=20, 1 no model; intervals overlap |
| faults, independent seeds 101 to 105 | noisy_channel | swarm ends with no trusted model in some runs | 1/20 runs; the swarm median covers only the rest |
| faults, independent seeds 101 to 105 | noisy_channel | swarm structure wrong | 7/20 runs |
| faults, independent seeds 101 to 105 | noisy_channel, arm | single_probe beats the swarm | 3.2 [2.3 to 227.5] n=5 vs swarm 3.9 [2.8 to 4.4] n=5, 1 no model; intervals overlap |
| faults, independent seeds 101 to 105 | noisy_channel, arm | pipeline beats the swarm | 3.5 [2.8 to 4.2] n=5 vs swarm 3.9 [2.8 to 4.4] n=5, 1 no model; intervals overlap |
| faults, independent seeds 101 to 105 | noisy_channel, arm | swarm ends with no trusted model in some runs | 1/5 runs; the swarm median covers only the rest |
| faults, independent seeds 101 to 105 | noisy_channel, arm | swarm structure wrong | 1/5 runs |
| faults, independent seeds 101 to 105 | noisy_channel, gantry | swarm structure wrong | 4/5 runs |
| faults, independent seeds 101 to 105 | noisy_channel, gantry | swarm median over 10 mm | 20.7 [4.4 to 29.7] n=5 |
| faults, independent seeds 101 to 105 | noisy_channel, scara | single_probe beats the swarm | 3.0 [1.3 to 31.1] n=5 vs swarm 5.1 [4.1 to 40.6] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | noisy_channel, scara | pipeline beats the swarm | 2.9 [2.3 to 31.5] n=5 vs swarm 5.1 [4.1 to 40.6] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | noisy_channel, scara | swarm structure wrong | 1/5 runs |
| faults, independent seeds 101 to 105 | noisy_channel, telescope | single_probe beats the swarm | 3.7 [1.3 to 327.5] n=5 vs swarm 5.3 [2.9 to 31.8] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | noisy_channel, telescope | pipeline beats the swarm | 3.4 [1.5 to 36.8] n=5 vs swarm 5.3 [2.9 to 31.8] n=5; intervals overlap |
| faults, independent seeds 101 to 105 | noisy_channel, telescope | swarm structure wrong | 1/5 runs |
| noise | 1, gantry | single_probe beats the swarm | 0.6 [0.4 to 1.1] n=5 vs swarm 0.6 [0.6 to 1.4] n=5; intervals overlap |
| noise | 1, scara | single_probe beats the swarm | 1.0 [0.6 to 1.4] n=5 vs swarm 1.0 [0.6 to 1.1] n=5; intervals overlap |
| noise | 2 | single_probe beats the swarm | 1.5 [1.2 to 1.7] n=20 vs swarm 1.7 [1.3 to 2.0] n=20; intervals overlap |
| noise | 2, arm | pipeline beats the swarm | 2.1 [1.6 to 3.7] n=5 vs swarm 2.1 [1.6 to 3.1] n=5; intervals overlap |
| noise | 2, gantry | single_probe beats the swarm | 0.9 [0.9 to 1.6] n=5 vs swarm 1.9 [1.2 to 2.6] n=5; intervals overlap |
| noise | 2, gantry | pipeline beats the swarm | 1.2 [1.1 to 2.3] n=5 vs swarm 1.9 [1.2 to 2.6] n=5; intervals overlap |
| noise | 5 | single_probe beats the swarm | 2.4 [2.2 to 3.4] n=20 vs swarm 3.7 [2.9 to 4.3] n=20; intervals overlap |
| noise | 5 | pipeline beats the swarm | 3.3 [2.6 to 4.2] n=20 vs swarm 3.7 [2.9 to 4.3] n=20; intervals overlap |
| noise | 5, arm | single_probe beats the swarm | 4.0 [2.2 to 4.7] n=5 vs swarm 4.2 [3.6 to 5.5] n=5; intervals overlap |
| noise | 5, arm | pipeline beats the swarm | 3.9 [2.8 to 6.3] n=5 vs swarm 4.2 [3.6 to 5.5] n=5; intervals overlap |
| noise | 5, gantry | single_probe beats the swarm | 2.2 [2.0 to 3.3] n=5 vs swarm 2.8 [1.9 to 6.5] n=5; intervals overlap |
| noise | 5, gantry | pipeline beats the swarm | 2.4 [2.3 to 5.4] n=5 vs swarm 2.8 [1.9 to 6.5] n=5; intervals overlap |
| noise | 5, scara | single_probe beats the swarm | 2.1 [1.9 to 4.1] n=5 vs swarm 3.0 [2.4 to 5.6] n=5; intervals overlap |
| noise | 5, telescope | single_probe beats the swarm | 3.4 [1.7 to 234.4] n=5 vs swarm 3.9 [3.4 to 5.3] n=5; intervals overlap |
| noise | 5, telescope | pipeline beats the swarm | 3.3 [2.4 to 6.4] n=5 vs swarm 3.9 [3.4 to 5.3] n=5; intervals overlap |
| noise | 10 | swarm structure wrong | 7/20 runs |
| noise | 10, gantry | swarm structure wrong | 2/5 runs |
| noise | 10, gantry | swarm median over 10 mm | 13.8 [5.3 to 24.8] n=5 |
| noise | 10, scara | swarm structure wrong | 3/5 runs |
| noise | 10, scara | swarm median over 10 mm | 27.5 [5.2 to 35.7] n=5 |
| noise | 10, telescope | swarm structure wrong | 2/5 runs |
| learning | 8 motions | single beats the swarm | 91.2 [9.1 to 302.4] n=10 vs swarm no model n=10; the swarm has no model yet |
| learning | 12 motions | single beats the swarm | 4.7 [3.2 to 6.7] n=10 vs swarm 171.4 [171.4 to 171.4] n=10, 9 no model; intervals do not overlap |
| learning | 12 motions | swarm ends with no trusted model in some runs | 9/10 runs; the swarm median covers only the rest |
| learning | 12 motions | swarm median over 10 mm | 171.4 [171.4 to 171.4] n=10, 9 no model |
| learning | 16 motions | single beats the swarm | 4.4 [2.5 to 6.2] n=10 vs swarm 196.9 [8.5 to 351.5] n=10, 4 no model; intervals do not overlap |
| learning | 16 motions | swarm ends with no trusted model in some runs | 4/10 runs; the swarm median covers only the rest |
| learning | 16 motions | swarm median over 10 mm | 196.9 [8.5 to 351.5] n=10, 4 no model |
| learning | 24 motions | single beats the swarm | 2.5 [1.9 to 3.0] n=10 vs swarm 5.1 [3.1 to 6.0] n=10, 2 no model; intervals do not overlap |
| learning | 24 motions | swarm ends with no trusted model in some runs | 2/10 runs; the swarm median covers only the rest |
| learning | 32 motions | single beats the swarm | 2.7 [1.8 to 3.2] n=10 vs swarm 3.1 [2.0 to 4.5] n=10; intervals overlap |
| learning | 48 motions | single beats the swarm | 1.5 [1.4 to 2.5] n=10 vs swarm 2.7 [1.6 to 3.4] n=10; intervals overlap |
| learning | 64 motions | single beats the swarm | 1.5 [1.0 to 2.3] n=10 vs swarm 2.4 [1.6 to 3.4] n=10; intervals overlap |
