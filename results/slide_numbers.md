# Slide numbers

Every number the slides may quote, with its n and the `results/summary.md` section it comes from. Reach error is
the median miss on held-out reachable targets in mm, with the bootstrap 95% CI of the median in brackets.
"Independent seeds" are 101 to 105, added after the swarm v2 fixes were designed; quote them first. Frozen at tag
`results-final`.

## 1. The mystery: a body nobody describes

- Told nothing about the body (not even arm, gantry, SCARA or telescope), the swarm found every joint's type and axis on 20/20 robots on the independent seeds and 40/40 on the original seeds. n = 60 robots. Source: §1 Unknown body types, rows "all".
- A single agent searching blind found it on 5/20 (independent) and 6/40 (original). Source: §1, rows "all".
- Real arms (Franka Panda, UR5e, Kinova Gen3, ViperX 300s, channels shuffled): the swarm gets every observable joint right in all 8 arm × channel settings (e.g. Panda shuffled 18/18 observable, 19/21 all joints); the single agent gets 2/16 to 11/18 observable. n = 3 seeds per setting. Source: §2 Real arms.

## 2. Live structure discovery

- Swarm reach error after 64 motions: 1.5 [1.4 to 1.9] mm, n = 20 (independent seeds); 1.6 [1.3 to 2.0] mm, n = 40 (original). Source: §1, rows "all".
- The swarm spends 36 [32 to 40] of its 64 motions sweeping one channel at a time (home and bent pose per channel, plus review rechecks), n = 60. Source: §10 Cost, row "bodies | swarm".
- Real arms: swarm reach 1.9 to 2.6 mm (median per arm and channel order, n = 3 each) vs the single agent's 270 to 592 mm. Source: §2.
- Every crowned final champion (no fault, n = 40 runs) descends from 7 (6 to 8) distinct agent types, and in 39 of 40 it was fit with structures proposed by two or more sources that disagreed. Source: §11 Provenance, row "faults | none | swarm".

## 3. Secret damage

- The swarm noticed the damage in 97/120 runs (81%); pipeline 95/120. Detected on 20/20 runs for locked joint, long link, reversed motor and tool; 16/20 for bent axis; 1/20 for payload. Source: §3 Damage.
- Detection latency: median 26 to 32 motions after the damage for the five kinds other than payload (n = 16 to 20 detected runs per kind; payload's one detection came at 51). Source: §3, swarm latency column.
- Cube pick and place, damage (long link) at motion 48: swarm 20/20 before and 20/20 after (place error 2.9 [2.3 to 3.7] then 4.7 [2.4 to 6.5] mm, it asked for a replan in all 20); single agent 20/20 before, 4/20 after (149.1 [54.9 to 376.0] mm). n = 20 arms. Source: §4 Cube task.
- Honest limit: at motion 128 (64 motions after the damage) the swarm has a trusted model in only 59/120 runs; the pipeline in 112/120, both single agents in 120/120. Source: §3, "Runs with a trusted model".

## 4. Scale

- 1938 sweep jobs (240 bodies, 480 damage, 800 faults, 320 noise, 48 real arm, 30 learning, 20 extrapolation), 0 left to run; one job errored once (a scipy SVD failure in a validator replay), was fixed and rerun. Source: summary header and "Jobs that errored".
- Extrapolation guard: refuses 200/200 out-of-reach targets and 0/200 reachable ones; a planner without it misses out-of-reach targets by 466 [452 to 517] mm. n = 200 each. Source: §8.
- Camera noise: at 10 mm the swarm ends at 9.1 [6.4 to 21.2] mm vs single 50.0, single_probe 43.1, pipeline 31.0 mm (n = 20 each); zero false alarms at any noise level (0/20 each). Source: §6.

## 5. Is the swarm necessary? (independent seeds, n = 20 robots per cell)

- One channel agent reports a wrong joint type: swarm 1.5 [1.4 to 2.0] mm, structure 20/20; single_probe 43.8 mm (1/20); pipeline 41.4 mm (3/20). Source: §5 Injected faults, independent seeds, row wrong_finding.
- A confident wrong hypothesis source: swarm 1.6 [1.3 to 1.9] mm, 20/20; pipeline 27.4 mm, 0/20 (its LLM stage has the final say). Source: §5, row bad_llm.
- One chain modeler crashes at motion 24: swarm 1.7 [1.4 to 2.2] mm, 20/20; pipeline has no model in 18/20; single_probe 3.2 mm. Source: §5, row modeler_crash.
- Knockout: removing any one agent type at motion 24 (11 cases) leaves the structure right in 20/20 every time. Source: §7 Knockout.
- Where it is not needed: with no fault, single_probe 1.3 [1.0 to 1.7] and pipeline 1.7 [1.0 to 2.0] mm tie the swarm's 1.5 [1.4 to 1.9] mm. Source: §5 row none and §1, plus Ties.

## 6. Failures we found

- A noisy sensor on one channel (20 mm on every sweep of it): swarm 5.1 mm, structure 13/20; single_probe and pipeline 3.7 mm (independent seeds). Source: §5, row noisy_channel; Failures we found.
- After damage the swarm re-learns slowly: trusted model at motion 128 in 59/120 runs vs pipeline 112/120. Source: §3.
- Payload damage is noticed in 1/20 runs. Source: §3.
- Known arms (nothing to discover): the single agent beats the swarm at every checkpoint, 1.5 [1.0 to 2.3] vs 2.4 [1.6 to 3.4] mm at 64 motions, n = 10 arms. Source: §9.
- Cost: 91.5 [73.3 to 104.6] agent CPU seconds per robot for the swarm vs 5.8 (pipeline) to 9.4 (single_probe), n = 60. Source: §10, rows "bodies".
- One validator replay crashed the whole run once (scipy SVD); fixed so a failed replay fails the check. Source: "Jobs that errored".

## 7. How it works

- Agents: 2 explorers, 2 channel agents per channel (home and bent pose), a review agent (third pose), hypothesizers (findings, prior, library, one LLM per key), 4 modelers (2 chain, GMM, MLP), 2 validators voting on the public crowning rule, a monitor. The review agent and the monitor are single instances; knocking out the review agent still leaves 20/20 structures right (§7).
- The v2 fixes (replicated channel agents, review agent, second chain modeler) were designed after the fault preview on seeds 1 and 2; seeds 101 to 105 are the independent check. Source: summary "Read this first".

## 8. What is next

- Re-learn faster after damage (59/120 runs with a trusted model at motion 128). Source: §3.
- Cross-check sweeps against mixed motions so a sensor that is wrong every time can be outvoted (noisy_channel). Source: §5.
- Cut CPU (91.5 s per robot vs 5.8 s for the pipeline). Source: §10.
- Vision: two cameras instead of a marker, median triangulation error 3.0 to 4.3 mm per family. Source: §13 Vision. Dynamics results are from the swarm before v2 and were not rerun. Source: §12.

## Headline numbers that changed since the 418 job run (commit 6630461, results/sweep/summary.md)

Baseline rows (single, mlp) reuse the same jobs and did not change. Every change below is a swarm number, from swarm v2.

- Unknown bodies, original seeds, swarm reach (structure still 10/10 per family): arm 1.8 → 2.1 mm, gantry 1.1 → 1.8, scara 1.3 → 1.4, telescope 1.3 → 1.7.
- Damage, swarm detected: bent axis 18/20 → 16/20, payload 0/20 → 1/20 (other kinds 20/20 in both).
- Damage, swarm detection latency (median motions after the damage): bent axis 5.5 → 26, locked joint 2.0 → 26, long link 2.0 → 28, reversed motor 2.5 → 32, tool 2.0 → 26 (same definition in both; cause not investigated).
- Damage, swarm error at the end: bent axis 1.3 → 2.3, locked joint 1.5 → 1.7, long link 1.6 → 1.3, payload 2.2 → 2.3, reversed motor 1.6 → 1.6, tool 1.5 → 1.8 mm. New: these now report that 10 to 13 of 20 swarm runs per detected kind have no model at the end; the old table did not count them.
- Real arms, swarm reach: Panda ordered 1.9 → 2.1, shuffled 2.3 → 2.6; UR5e ordered 2.2 → 1.9, shuffled 1.6 → 2.0; Gen3 ordered 2.4 → 2.1, shuffled 2.2 → 2.0; vx300s ordered 2.3 → 2.4, shuffled 2.1 → 2.0 mm.
- Real arms, swarm joints right: Panda ordered 18/21 → 19/21, UR5e shuffled 16/18 → 15/18, Gen3 ordered 20/21 → 19/21, Gen3 shuffled 18/21 → 19/21, vx300s ordered 15/18 → 16/18, vx300s shuffled 15/18 → 16/18 (observable joints still all right).
- Extrapolation: refusal rates unchanged (0% reachable, 100% out of reach); naive miss on reachable targets 1 → 2 mm (all, gantry, scara, telescope).
- Learning on known arms, swarm: 16 motions 17.2 → 196.9 mm (4 of 10 runs with no model), 24 motions 3.9 → 5.1, 32 motions 3.4 → 3.1, 48 motions 2.5 → 2.7, 64 motions 2.1 → 2.4 mm.
- New since 6630461 (no earlier number): pipeline and single_probe conditions, independent seeds, faults, noise, knockout on v2, cube task on v2, cost and provenance.
