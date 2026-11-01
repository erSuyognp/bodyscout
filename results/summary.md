# BodyScout results summary

Generated 2026-11-01 by `experiments/make_plots.py results/sweep` at commit b4f902c. Sweep: `results/sweep.jsonl`, 2152 job lines, sha256 c716e2805290. This file and `results/sweep/summary.md` are the same file; the slides quote only numbers in it.

Cells: median [bootstrap 95% CI of the median, 2000 resamples] n = runs. Rates: k/n (percent). Reach error is the median miss on held-out reachable targets, in mm, scored on the true body.

**Read this first.** The swarm v2 fixes (two channel agents per channel probing from different poses, a review agent that rechecks doubtful channels from a third pose, a second chain modeler) were designed after we saw the fault preview on seeds 1 and 2 of the gantry and SCARA families, where one wrong channel finding or one crashed chain modeler sank the swarm. Seeds 101 and up were added after those fixes and are the independent check: tables split by seed show them separately. Swarm rows without swarm_version 2 in their meta come from the swarm before the fixes.

## Jobs that errored during the sweep

| job | error | status |
| --- | --- | --- |
| damage|family=gantry|seed=3|damage=tool|condition=swarm|swarm=v2 | numpy.linalg.LinAlgError: SVD did not converge | completed on a rerun after the fix below |

Cause and fix: scipy's SVD failed inside a validator's replay refit, and `Validator._replay` had no guard, so one numerical failure ended the whole run. A replay that fails now counts as a failed check (that candidate cannot be crowned). The fix changes only runs in which a replay failed, so every job that had already completed is unchanged; only the jobs above were rerun.

## 1. Unknown body types, original seeds 1 to 10

Told nothing about the body. Structure right = every joint's type and axis; reach error at 64 motions.

| body | swarm structure right | single structure right | single_probe structure right | pipeline structure right | swarm reach mm | single reach mm | single_probe reach mm | pipeline reach mm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arm | 10/10 (100%) | 1/10 (10%) | 10/10 (100%) | 10/10 (100%) | 2.1 [1.6 to 2.8] n=10 | 220.8 [138.1 to 319.2] n=10 | 2.1 [1.4 to 2.6] n=10 | 2.1 [1.7 to 3.0] n=10 |
| gantry | 10/10 (100%) | 1/10 (10%) | 10/10 (100%) | 10/10 (100%) | 1.8 [1.2 to 2.4] n=10 | 59.2 [37.4 to 94.2] n=10 | 0.9 [0.8 to 1.1] n=10 | 1.2 [1.1 to 1.5] n=10 |
| scara | 10/10 (100%) | 2/10 (20%) | 10/10 (100%) | 10/10 (100%) | 1.4 [1.1 to 1.6] n=10 | 41.4 [17.8 to 101.0] n=10 | 1.3 [1.1 to 1.6] n=10 | 1.6 [1.1 to 1.8] n=10 |
| telescope | 10/10 (100%) | 2/10 (20%) | 10/10 (100%) | 10/10 (100%) | 1.7 [1.2 to 2.1] n=10 | 48.5 [20.0 to 205.3] n=10 | 1.6 [1.3 to 1.8] n=10 | 1.7 [1.3 to 2.2] n=10 |
| all | 40/40 (100%) | 6/40 (15%) | 40/40 (100%) | 40/40 (100%) | 1.6 [1.3 to 2.0] n=40 | 79.4 [45.0 to 109.2] n=40 | 1.4 [1.2 to 1.6] n=40 | 1.6 [1.4 to 1.9] n=40 |

## 1. Unknown body types, independent seeds 101 to 105

Told nothing about the body. Structure right = every joint's type and axis; reach error at 64 motions.

| body | swarm structure right | single structure right | single_probe structure right | pipeline structure right | swarm reach mm | single reach mm | single_probe reach mm | pipeline reach mm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arm | 5/5 (100%) | 2/5 (40%) | 5/5 (100%) | 5/5 (100%) | 1.8 [0.8 to 2.8] n=5 | 40.5 [0.8 to 431.2] n=5 | 1.6 [1.0 to 2.2] n=5 | 2.5 [0.9 to 2.7] n=5 |
| gantry | 5/5 (100%) | 1/5 (20%) | 5/5 (100%) | 5/5 (100%) | 1.3 [0.9 to 1.5] n=5 | 64.2 [1.0 to 104.3] n=5 | 0.9 [0.7 to 1.0] n=5 | 1.0 [0.8 to 1.3] n=5 |
| scara | 5/5 (100%) | 1/5 (20%) | 5/5 (100%) | 5/5 (100%) | 1.8 [0.9 to 2.0] n=5 | 39.3 [1.5 to 77.3] n=5 | 1.2 [0.7 to 2.6] n=5 | 1.8 [0.9 to 2.0] n=5 |
| telescope | 5/5 (100%) | 1/5 (20%) | 5/5 (100%) | 5/5 (100%) | 1.6 [1.4 to 2.3] n=5 | 45.9 [1.3 to 182.3] n=5 | 1.6 [1.4 to 2.2] n=5 | 2.1 [1.7 to 2.2] n=5 |
| all | 20/20 (100%) | 5/20 (25%) | 20/20 (100%) | 20/20 (100%) | 1.5 [1.4 to 1.9] n=20 | 45.4 [34.4 to 74.3] n=20 | 1.3 [1.0 to 1.7] n=20 | 1.7 [1.0 to 2.0] n=20 |

All seeds pooled, as drawn in fig_bodies (reach error at 64 motions, mm):

| body | swarm | single | single_probe | pipeline |
| --- | --- | --- | --- | --- |
| arm | 2.1 [1.4 to 2.8] n=15 | 202.2 [74.0 to 256.0] n=15 | 1.9 [1.3 to 2.4] n=15 | 2.1 [1.6 to 2.5] n=15 |
| gantry | 1.5 [1.2 to 1.9] n=15 | 64.2 [44.4 to 88.1] n=15 | 0.9 [0.9 to 1.0] n=15 | 1.1 [1.0 to 1.3] n=15 |
| scara | 1.5 [1.1 to 1.6] n=15 | 39.3 [20.8 to 77.3] n=15 | 1.2 [1.0 to 1.6] n=15 | 1.6 [1.1 to 1.8] n=15 |
| telescope | 1.6 [1.4 to 2.0] n=15 | 46.4 [30.1 to 182.3] n=15 | 1.6 [1.4 to 1.7] n=15 | 2.0 [1.4 to 2.2] n=15 |

## 2. Real arms from MuJoCo Menagerie, body type unknown

Channels in the robot's own order and shuffled. Joints right counts every joint over the seeds; observable = joints whose type the fingertip can reveal.

| arm | channels | swarm reach mm | single reach mm | swarm joints right | single joints right |
| --- | --- | --- | --- | --- | --- |
| panda | ordered | 2.1 [1.7 to 2.5] n=3 | 340.3 [309.1 to 433.8] n=3 | 19/21 (90%); observable 18/18 | 11/21 (52%); observable 11/18 |
| panda | shuffled | 2.6 [1.4 to 3.2] n=3 | 505.9 [359.5 to 684.8] n=3 | 19/21 (90%); observable 18/18 | 5/21 (24%); observable 5/18 |
| ur5e | ordered | 1.9 [1.3 to 2.5] n=3 | 285.2 [221.9 to 473.7] n=3 | 16/18 (89%); observable 15/15 | 8/18 (44%); observable 7/15 |
| ur5e | shuffled | 2.0 [2.0 to 2.1] n=3 | 348.3 [252.4 to 455.6] n=3 | 15/18 (83%); observable 15/15 | 5/18 (28%); observable 5/15 |
| gen3 | ordered | 2.1 [2.0 to 3.5] n=3 | 392.3 [299.6 to 832.4] n=3 | 19/21 (90%); observable 16/16 | 11/21 (52%); observable 8/16 |
| gen3 | shuffled | 2.0 [1.9 to 2.5] n=3 | 591.6 [398.0 to 837.1] n=3 | 19/21 (90%); observable 16/16 | 2/21 (10%); observable 2/16 |
| vx300s | ordered | 2.4 [1.8 to 2.7] n=3 | 296.7 [113.2 to 332.3] n=3 | 16/18 (89%); observable 15/15 | 7/18 (39%); observable 7/15 |
| vx300s | shuffled | 2.0 [1.9 to 3.8] n=3 | 270.1 [227.4 to 443.5] n=3 | 16/18 (89%); observable 15/15 | 5/18 (28%); observable 5/15 |

## 3. Damage mid run (break at motion 64; arm, gantry, scara, telescope, body type unknown)

Detected = an alarm at or after the damage (alarms before it are false alarms and do not count). Latency = motions from the damage to the first such alarm. Recovered error = reach error at 128 motions.

| damage | swarm detected | swarm latency, motions | pipeline detected | pipeline latency, motions | swarm recovered error mm | single recovered error mm | single_probe recovered error mm | pipeline recovered error mm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bent_axis | 16/20 (80%) | 26 [6 to 39] n=16 | 15/20 (75%) | 29 [29 to 42] n=15 | 2.3 [1.6 to 7.1] n=20, 10 no model | 46.3 [39.9 to 69.3] n=20 | 7.3 [6.3 to 8.8] n=20 | 2.4 [1.9 to 4.6] n=20, 4 no model |
| locked_joint | 20/20 (100%) | 26 [6 to 38] n=20 | 20/20 (100%) | 29 [29 to 29] n=20 | 1.7 [1.3 to 2.4] n=20, 12 no model | 45.4 [32.8 to 63.6] n=20 | 20.2 [13.3 to 30.9] n=20 | 2.2 [2.0 to 2.6] n=20, 3 no model |
| long_link | 20/20 (100%) | 28 [6 to 38] n=20 | 20/20 (100%) | 29 [29 to 29] n=20 | 1.3 [1.0 to 2.8] n=20, 13 no model | 55.9 [40.3 to 77.5] n=20 | 30.1 [26.1 to 37.6] n=20 | 2.4 [1.9 to 2.7] n=20 |
| payload | 1/20 (5%) | 51 [51 to 51] n=1 | 0/20 (0%) | none detected | 2.3 [1.6 to 2.7] n=20, 1 no model | 37.2 [28.7 to 65.6] n=20 | 1.6 [1.2 to 2.7] n=20 | 2.0 [1.7 to 3.2] n=20 |
| reversed_motor | 20/20 (100%) | 32 [6 to 38] n=20 | 20/20 (100%) | 29 [29 to 29] n=20 | 1.6 [0.9 to 2.0] n=20, 13 no model | 77.0 [55.3 to 98.9] n=20 | 42.2 [36.7 to 46.9] n=20 | 2.0 [1.5 to 2.5] n=20, 1 no model |
| tool | 20/20 (100%) | 26 [6 to 38] n=20 | 20/20 (100%) | 29 [29 to 29] n=20 | 1.8 [1.5 to 2.5] n=20, 12 no model | 88.0 [71.5 to 112.9] n=20 | 40.9 [37.4 to 42.2] n=20 | 2.4 [2.1 to 2.9] n=20 |

All kinds: swarm detected 97/120 (81%); pipeline detected 95/120 (79%).
Runs with a trusted model at motion 128: swarm 59/120 (49%); single 120/120 (100%); single_probe 120/120 (100%); pipeline 112/120 (93%). Recovered error and the curves in fig_damage are medians over the runs that have a model at that point, so read them together with this count. Between the alarm and the next crowned model the planner has no trusted model and refuses to move.

## 4. Cube pick and place before and after damage

Source: `results/task.csv`, regenerated in this working tree (code at b4f902c). One trial per arm seed; damage (long link) at motion 48. Place error is measured only where the cube was placed.

| condition | phase | success | place error mm | replans asked |
| --- | --- | --- | --- | --- |
| swarm | before | 20/20 (100%) | 2.9 [2.3 to 3.7] n=20 | 0 |
| swarm | after | 20/20 (100%) | 4.7 [2.4 to 6.5] n=20 | 20 |
| single | before | 20/20 (100%) | 3.1 [2.0 to 4.7] n=20 | 0 |
| single | after | 4/20 (20%) | 149.1 [54.9 to 376.0] n=20 | 0 |

## 5. Injected faults, original seeds 1 to 5

20 robots (arm, gantry, scara, telescope), reach error at 64 motions.

| fault | swarm reach mm | single reach mm | single_probe reach mm | pipeline reach mm | swarm structure right | single structure right | single_probe structure right | pipeline structure right |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 1.7 [1.3 to 2.0] n=20 | 48.8 [44.1 to 192.8] n=20 | 1.5 [1.2 to 1.7] n=20 | 1.8 [1.4 to 2.1] n=20 | 20/20 (100%) | 4/20 (20%) | 20/20 (100%) | 20/20 (100%) |
| wrong_finding | 1.6 [1.4 to 1.9] n=20 | 48.8 [44.1 to 192.8] n=20 (no slot: fault never fired) | 61.5 [36.1 to 125.2] n=20 | 60.5 [33.5 to 119.9] n=20 | 20/20 (100%) | 4/20 (20%) | 1/20 (5%) | 1/20 (5%) |
| bad_llm | 1.5 [1.3 to 1.9] n=20 | 48.8 [44.1 to 192.8] n=20 (no slot: fault never fired) | 1.5 [1.2 to 1.7] n=20 (no slot: fault never fired) | 30.8 [24.3 to 34.4] n=20 | 20/20 (100%) | 4/20 (20%) | 20/20 (100%) | 0/20 (0%) |
| modeler_crash | 1.6 [1.3 to 1.8] n=20 | 67.6 [37.4 to 117.1] n=20 | 2.8 [2.0 to 3.3] n=20 | no model n=20 | 20/20 (100%) | 3/20 (15%) | 20/20 (100%) | 0/20 (0%) |
| noisy_channel | 5.5 [4.3 to 9.3] n=20 | 48.8 [44.1 to 192.8] n=20 (no slot: fault never fired) | 3.0 [2.3 to 3.4] n=20 | 3.2 [2.5 to 5.1] n=20 | 15/20 (75%) | 4/20 (20%) | 15/20 (75%) | 15/20 (75%) |

Probe motions per run (single channel sweeps among the motions), all settings: swarm 40 [36 to 40] n=100; single 0 [0 to 0] n=100; single_probe 16 [16 to 16] n=100; pipeline 16 [16 to 16] n=100.

## 5. Injected faults, independent seeds 101 to 105

20 robots (arm, gantry, scara, telescope), reach error at 64 motions.

| fault | swarm reach mm | single reach mm | single_probe reach mm | pipeline reach mm | swarm structure right | single structure right | single_probe structure right | pipeline structure right |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 1.5 [1.4 to 1.9] n=20 | 45.4 [34.4 to 74.3] n=20 | 1.3 [1.0 to 1.7] n=20 | 1.7 [1.0 to 2.0] n=20 | 20/20 (100%) | 5/20 (25%) | 20/20 (100%) | 20/20 (100%) |
| wrong_finding | 1.5 [1.4 to 2.0] n=20 | 45.4 [34.4 to 74.3] n=20 (no slot: fault never fired) | 43.8 [37.8 to 66.6] n=20 | 41.4 [26.6 to 71.1] n=20 | 20/20 (100%) | 5/20 (25%) | 1/20 (5%) | 3/20 (15%) |
| bad_llm | 1.6 [1.3 to 1.9] n=20 | 45.4 [34.4 to 74.3] n=20 (no slot: fault never fired) | 1.3 [1.0 to 1.7] n=20 (no slot: fault never fired) | 27.4 [17.9 to 34.0] n=20, 1 no model | 20/20 (100%) | 5/20 (25%) | 20/20 (100%) | 0/20 (0%) |
| modeler_crash | 1.7 [1.4 to 2.2] n=20 | 54.2 [31.8 to 90.2] n=20 | 3.2 [2.6 to 4.1] n=20 | 2.4 [1.8 to 3.0] n=20, 18 no model | 20/20 (100%) | 3/20 (15%) | 20/20 (100%) | 2/20 (10%) |
| noisy_channel | 5.1 [4.4 to 18.6] n=20, 1 no model | 45.4 [34.4 to 74.3] n=20 (no slot: fault never fired) | 3.7 [2.5 to 31.2] n=20 | 3.7 [3.0 to 11.0] n=20 | 13/20 (65%) | 5/20 (25%) | 12/20 (60%) | 14/20 (70%) |

Probe motions per run (single channel sweeps among the motions), all settings: swarm 32 [32 to 36] n=100; single 0 [0 to 0] n=100; single_probe 16 [16 to 16] n=100; pipeline 16 [16 to 16] n=100.

wrong_finding flips one channel's reported joint type (the home pose channel agent); bad_llm posts 3 confident wrong structures every epoch in an LLM's slot (the pipeline's LLM stage has the final say, so it adopts them); modeler_crash stops one chain modeler at motion 24; noisy_channel adds 20 mm noise to every sweep of one channel. Faults hit one agent instance; the swarm's replicas and second chain modeler are not faulted. 'No slot' means the condition has no place for that fault (a single agent has no findings and no hypothesis source), so it ran unchanged.

## 6. Camera noise sweep

20 robots (arm, gantry, scara, telescope), reach error at 64 motions.

| noise mm | swarm reach mm | single reach mm | single_probe reach mm | pipeline reach mm | swarm structure right | single structure right | single_probe structure right | pipeline structure right |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1.0 [0.8 to 1.3] n=20 | 43.1 [37.8 to 197.5] n=20 | 1.1 [0.9 to 1.3] n=20 | 1.1 [0.9 to 1.5] n=20 | 20/20 (100%) | 4/20 (20%) | 20/20 (100%) | 20/20 (100%) |
| 2 | 1.7 [1.3 to 2.0] n=20 | 48.8 [44.1 to 192.8] n=20 | 1.5 [1.2 to 1.7] n=20 | 1.8 [1.4 to 2.1] n=20 | 20/20 (100%) | 4/20 (20%) | 20/20 (100%) | 20/20 (100%) |
| 5 | 3.7 [2.9 to 4.3] n=20 | 55.9 [35.7 to 178.6] n=20 | 2.4 [2.2 to 3.4] n=20 | 3.3 [2.6 to 4.2] n=20 | 20/20 (100%) | 4/20 (20%) | 19/20 (95%) | 20/20 (100%) |
| 10 | 9.1 [6.4 to 21.2] n=20 | 50.0 [35.9 to 176.1] n=20 | 43.1 [28.3 to 65.1] n=20 | 31.0 [21.5 to 50.2] n=20 | 13/20 (65%) | 4/20 (20%) | 3/20 (15%) | 4/20 (20%) |

Probe motions per run (single channel sweeps among the motions), all settings: swarm 40 [32 to 40] n=80; single 0 [0 to 0] n=80; single_probe 16 [16 to 16] n=80; pipeline 16 [16 to 16] n=80.

False alarms (the monitor declared damage on an undamaged body), runs with any:

| noise mm | swarm | pipeline |
| --- | --- | --- |
| 1 | 0/20 (0%) | 0/20 (0%) |
| 2 | 0/20 (0%) | 0/20 (0%) |
| 5 | 0/20 (0%) | 0/20 (0%) |
| 10 | 0/20 (0%) | 0/20 (0%) |

## 7. Knockout: one agent type removed mid run

Source: `results/knockout.csv`, regenerated in this working tree (code at b4f902c). Removed at motion 24; unknown bodies (arm, gantry, scara, telescope).

| removed | structure right | reach at 64 motions mm | change vs full, mm | runs with no model | validator disagreements |
| --- | --- | --- | --- | --- | --- |
| full collective | 20/20 (100%) | 1.7 [1.3 to 2.0] n=20 |  | 0 | 0 |
| no findings hypothesizer | 20/20 (100%) | 1.4 [1.3 to 2.0] n=20 | -0.2 | 0 | 0 |
| no prior hypothesizer | 20/20 (100%) | 1.4 [1.3 to 2.0] n=20 | -0.2 | 0 | 0 |
| no library hypothesizer | 20/20 (100%) | 1.4 [1.3 to 2.0] n=20 | -0.2 | 0 | 0 |
| one validator lost | 20/20 (100%) | 1.4 [1.2 to 2.0] n=20 | -0.3 | 0 | 0 |
| one explorer lost | 20/20 (100%) | 1.4 [1.3 to 1.6] n=20 | -0.3 | 0 | 0 |
| no monitor | 20/20 (100%) | 1.4 [1.3 to 1.8] n=20 | -0.2 | 0 | 0 |
| every hypothesizer lost | 20/20 (100%) | 1.6 [1.3 to 2.1] n=20 | -0.0 | 0 | 0 |
| one chain modeler lost | 20/20 (100%) | 1.6 [1.3 to 1.8] n=20 | -0.1 | 0 | 0 |
| bent pose channel agents lost | 20/20 (100%) | 1.6 [1.5 to 2.0] n=20 | -0.0 | 0 | 0 |
| review agent lost | 20/20 (100%) | 1.5 [1.4 to 2.0] n=20 | -0.2 | 0 | 0 |

## 8. Knowing when it is guessing (extrapolation guard)

Out of reach targets sit 1.3x beyond the largest possible reach. Refused = the planner declined; naive miss = how far a planner without the guard ends from the target.

| family | targets | BodyScout refused | naive planner miss mm |
| --- | --- | --- | --- |
| all | reachable | 0/200 (0%) | 2 [2 to 2] n=200 |
| all | out of reach | 200/200 (100%) | 466 [452 to 517] n=200 |
| arm | reachable | 0/50 (0%) | 2 [2 to 3] n=50 |
| arm | out of reach | 50/50 (100%) | 407 [326 to 458] n=50 |
| gantry | reachable | 0/50 (0%) | 2 [1 to 2] n=50 |
| gantry | out of reach | 50/50 (100%) | 804 [745 to 864] n=50 |
| scara | reachable | 0/50 (0%) | 2 [1 to 2] n=50 |
| scara | out of reach | 50/50 (100%) | 459 [450 to 505] n=50 |
| telescope | reachable | 0/50 (0%) | 2 [1 to 2] n=50 |
| telescope | out of reach | 50/50 (100%) | 376 [338 to 412] n=50 |

## 9. Learning curve on known arms (10 arms, structure known: nothing to discover)

The honest baseline comparison: when there is no structure to find, a single agent fitting every motion is as good or better.

| motions | swarm reach mm | single reach mm | mlp reach mm |
| --- | --- | --- | --- |
| 8 | no model n=10 | 91.2 [9.1 to 302.4] n=10 | no model n=10 |
| 12 | 171.4 [171.4 to 171.4] n=10, 9 no model | 4.7 [3.2 to 6.7] n=10 | no model n=10 |
| 16 | 196.9 [8.5 to 351.5] n=10, 4 no model | 4.4 [2.5 to 6.2] n=10 | 308.2 [192.4 to 398.0] n=10 |
| 24 | 5.1 [3.1 to 6.0] n=10, 2 no model | 2.5 [1.9 to 3.0] n=10 | 238.5 [161.2 to 332.0] n=10 |
| 32 | 3.1 [2.0 to 4.5] n=10 | 2.7 [1.8 to 3.2] n=10 | 214.8 [115.8 to 240.7] n=10 |
| 48 | 2.7 [1.6 to 3.4] n=10 | 1.5 [1.4 to 2.5] n=10 | 134.9 [107.2 to 182.7] n=10 |
| 64 | 2.4 [1.6 to 3.4] n=10 | 1.5 [1.0 to 2.3] n=10 | 163.0 [91.0 to 206.1] n=10 |

## 10. Cost per robot (one run = one robot)

Motions spent, of them single channel sweeps, and agent CPU seconds (process CPU in agent steps, scoring excluded; runs without the field predate it).

| experiment | condition | motions used | probe motions | agent CPU s |
| --- | --- | --- | --- | --- |
| bodies | swarm | 65 [64 to 65] n=60 | 36 [32 to 40] n=60 | 91.5 [73.3 to 104.6] n=60 |
| bodies | single | 64 [64 to 64] n=20 | 0 [0 to 0] n=20 | 8.4 [7.6 to 9.2] n=20 |
| bodies | single_probe | 64 [64 to 64] n=60 | 16 [16 to 16] n=60 | 9.4 [8.6 to 9.7] n=60 |
| bodies | pipeline | 68 [68 to 68] n=60 | 16 [16 to 16] n=60 | 5.8 [5.5 to 6.0] n=60 |
| damage | swarm | 129 [128 to 131] n=120 | 68 [64 to 72] n=120 | 161.9 [150.9 to 188.3] n=120 |
| damage | single_probe | 128 [128 to 128] n=120 | 16 [16 to 16] n=120 | 20.8 [20.0 to 22.0] n=120 |
| damage | pipeline | 132 [132 to 132] n=120 | 32 [32 to 32] n=120 | 12.0 [11.4 to 13.6] n=120 |
| faults | swarm | 65 [65 to 65] n=200 | 36 [32 to 40] n=200 | 71.9 [64.3 to 76.5] n=200 |
| faults | single | 64 [64 to 64] n=200 | 0 [0 to 0] n=200 | 8.6 [8.2 to 8.9] n=200 |
| faults | single_probe | 64 [64 to 64] n=200 | 16 [16 to 16] n=200 | 8.8 [8.5 to 9.3] n=200 |
| faults | pipeline | 68 [68 to 68] n=200 | 16 [16 to 16] n=200 | 6.0 [5.6 to 8.0] n=200 |
| noise | swarm | 65 [65 to 69] n=80 | 40 [32 to 40] n=80 | 80.4 [68.8 to 101.2] n=80 |
| noise | single | 64 [64 to 64] n=80 | 0 [0 to 0] n=80 | 10.2 [9.7 to 11.1] n=80 |
| noise | single_probe | 64 [64 to 64] n=80 | 16 [16 to 16] n=80 | 9.7 [8.9 to 15.9] n=80 |
| noise | pipeline | 68 [68 to 68] n=80 | 16 [16 to 16] n=80 | 6.5 [6.1 to 9.8] n=80 |
| learning | swarm | 67 [64 to 67] n=10 | n/a | 76.7 [69.8 to 85.0] n=10 |
| menagerie | swarm | 162 [161 to 162] n=24 | n/a | 1119.6 [888.4 to 1331.2] n=24 |

## 11. Provenance of crowned champions

Source: `results/provenance/provenance.md`, regenerated in this working tree (code at b4f902c) (from the saved blackboards; per champion rows in `results/provenance/champions.csv`).

Agent types: distinct agent types among a champion's ancestors, median (range). Competing: champions whose model was fit with hypotheses from two or more sources, and how many of those had sources whose first structures disagreed. Won: whose proposal the champion's structure came from (fit = no hypothesis had it). Pipeline authors are stages of one orchestrator, not independent agents.

Final champion of each run:

| experiment | setting | condition | champions | agent types | competing (disagreed) | won | structure right |
| --- | --- | --- | --- | --- | --- | --- | --- |
| damage | bent_axis | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | bent_axis | swarm | 20 | 8 (6 to 9) | 19 (19) | channels 20 | 20/20 |
| damage | locked_joint | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 17, fit 3 | 5/20 |
| damage | locked_joint | swarm | 20 | 8 (6 to 9) | 11 (11) | channels 17, fit 2, prior 1 | 16/20 |
| damage | long_link | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | long_link | swarm | 20 | 8 (6 to 9) | 19 (19) | channels 19, fit 1 | 20/20 |
| damage | payload | pipeline | 20 | 7 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | payload | swarm | 20 | 8 (6 to 9) | 19 (19) | channels 19, fit 1 | 20/20 |
| damage | reversed_motor | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | reversed_motor | swarm | 20 | 8 (4 to 9) | 16 (16) | channels 18, fit 2 | 19/20 |
| damage | tool | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | tool | swarm | 20 | 8 (5 to 9) | 17 (17) | channels 17, fit 3 | 19/20 |
| faults | bad_llm | pipeline | 40 | 7 (7 to 8) | 0 (0) | fit 40 | 0/40 |
| faults | bad_llm | swarm | 40 | 7 (6 to 8) | 38 (38) | channels 38, fit 2 | 40/40 |
| faults | modeler_crash | pipeline | 2 | 6 (6 to 6) | 0 (0) | channels 2 | 2/2 |
| faults | modeler_crash | swarm | 40 | 7 (6 to 8) | 39 (39) | channels 40 | 40/40 |
| faults | noisy_channel | pipeline | 40 | 6 (6 to 7) | 0 (0) | channels 35, fit 5 | 29/40 |
| faults | noisy_channel | swarm | 39 | 7 (3 to 9) | 29 (29) | channels 28, fit 10, prior 1 | 28/39 |
| faults | none | pipeline | 40 | 6 (6 to 7) | 0 (0) | channels 40 | 40/40 |
| faults | none | swarm | 40 | 7 (6 to 8) | 39 (39) | channels 40 | 40/40 |
| faults | wrong_finding | pipeline | 40 | 6 (6 to 7) | 0 (0) | fit 40 | 4/40 |
| faults | wrong_finding | swarm | 40 | 6 (6 to 7) | 1 (1) | channels 37, fit 2, prior 1 | 40/40 |
| noise | 1 mm | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| noise | 1 mm | swarm | 20 | 8 (7 to 8) | 20 (20) | channels 20 | 20/20 |
| noise | 10 mm | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 11, fit 9 | 4/20 |
| noise | 10 mm | swarm | 20 | 7 (4 to 8) | 12 (12) | fit 11, channels 7, prior 2 | 13/20 |
| noise | 2 mm | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| noise | 2 mm | swarm | 20 | 7 (7 to 8) | 20 (20) | channels 20 | 20/20 |
| noise | 5 mm | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 18, fit 2 | 20/20 |
| noise | 5 mm | swarm | 20 | 7 (7 to 8) | 20 (20) | channels 18, fit 2 | 20/20 |

## 12. Dynamics

Source: `results/summary_dynamics.md`, last changed in a58bb54 on 2026-10-31. These runs use the swarm before the v2 fixes (they predate them) and were not rerun.

### Dynamics change detection

Damage at motion 48: payload_dyn (+0.35 kg at the tip) or weak_motor (one joint, kp x 0.5). Watch window after damage: 40 motions. Body type unknown to the swarm. Identical swarms; only the monitor differs. A shape sentinel costs 1 motion, a dynamics sentinel (25 samples at 10 ms) costs 0.5.

#### In sample

Bodies: arm1, arm2, arm3, scara1, scara2. LLM hypothesizers: off (deterministic runs).

##### Detection

| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |
| --- | --- | --- | --- | --- | --- | --- |
| payload_dyn | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| payload_dyn | DynamicsMonitor | 4/5 | 13.0 | 0 | 4/5 | 3/5 |
| weak_motor | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| weak_motor | DynamicsMonitor | 2/5 | 15.0 | 0 | 2/5 | n/a |

##### Every run

| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm1 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm1 | 350 g payload in the gripper (dynamic) | dynamics | 9.0 | payload | 0.341 | n/a | 0 |
| arm1 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm1 | motor 2 lost half its stiffness | dynamics | 9.0 | weak motor 2 (truth 2) | n/a | 0.47 | 0 |
| arm2 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm2 | 350 g payload in the gripper (dynamic) | dynamics | 21.0 | payload | 0.347 | n/a | 0 |
| arm2 | motor 4 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm2 | motor 4 lost half its stiffness | dynamics | 21.0 | weak motor 4 (truth 4) | n/a | 0.49 | 0 |
| arm3 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm3 | 350 g payload in the gripper (dynamic) | dynamics | 17.0 | payload | 0.474 | n/a | 0 |
| arm3 | motor 4 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm3 | motor 4 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara1 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara1 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.348 | n/a | 0 |
| scara1 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara1 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara2 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara2 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara2 | motor 3 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara2 | motor 3 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |

##### Tip path error on fast moves, before damage (vs noise free truth)

| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |
| --- | --- | --- | --- | --- |
| arm1 | 234.6 | 6.5 | 0.400 | 0.309 |
| arm2 | 265.4 | 7.5 | 0.199 | 0.207 |
| arm3 | 265.9 | 14.4 | 0.642 | 0.205 |
| scara1 | 177.4 | 4.3 | 0.277 | 0.309 |
| scara2 | 124.9 | 2.0 | 0.207 | 0.207 |

#### Out of sample

New bodies with seeds no experiment or test had used. DynamicsMonitor and fit settings frozen at their committed values; nothing was tuned for or after these runs.
Bodies: arm101, arm102, arm103, arm104, arm105, scara101, scara102, scara103, telescope101, telescope102. LLM hypothesizers: off (deterministic runs).

##### Detection

| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |
| --- | --- | --- | --- | --- | --- | --- |
| payload_dyn | shape Monitor | 0/10 | n/a | 0 | does not name causes | n/a |
| payload_dyn | DynamicsMonitor | 4/10 | 11.0 | 0 | 4/10 | 3/10 |
| weak_motor | shape Monitor | 0/10 | n/a | 0 | does not name causes | n/a |
| weak_motor | DynamicsMonitor | 4/10 | 21.0 | 0 | 4/10 | n/a |

##### Every run

| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm102 | 350 g payload in the gripper (dynamic) | dynamics | 21.0 | payload | 0.345 | n/a | 0 |
| arm102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm102 | motor 2 lost half its stiffness | dynamics | 21.0 | weak motor 2 (truth 2) | n/a | 0.51 | 0 |
| arm103 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm103 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm103 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm103 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm104 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm104 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm104 | motor 3 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm104 | motor 3 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm105 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm105 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm105 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm105 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara102 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.342 | n/a | 0 |
| scara102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara102 | motor 2 lost half its stiffness | dynamics | 1.0 | weak motor 2 (truth 2) | n/a | 0.49 | 0 |
| scara103 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara103 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.550 | n/a | 0 |
| scara103 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara103 | motor 2 lost half its stiffness | dynamics | 25.5 | weak motor 2 (truth 2) | n/a | 0.49 | 0 |
| telescope101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| telescope101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| telescope101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| telescope102 | 350 g payload in the gripper (dynamic) | dynamics | 21.0 | payload | 0.418 | n/a | 0 |
| telescope102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| telescope102 | motor 2 lost half its stiffness | dynamics | 21.0 | weak motor 2 (truth 2) | n/a | 0.48 | 0 |

##### Tip path error on fast moves, before damage (vs noise free truth)

| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |
| --- | --- | --- | --- | --- |
| arm101 | 33.9 | 2.7 | 0.078 | 0.103 |
| arm102 | 182.0 | 6.7 | 0.172 | 0.105 |
| arm103 | no dynamics model by motion 48 | n/a | n/a | n/a |
| arm104 | no dynamics model by motion 48 | n/a | n/a | n/a |
| arm105 | 91.1 | 1.6 | 0.000 | 0.353 |
| scara101 | 140.1 | 2.6 | 0.260 | 0.103 |
| scara102 | 137.5 | 2.4 | 0.101 | 0.105 |
| scara103 | 167.4 | 3.2 | 0.044 | 0.066 |
| telescope101 | 127.6 | 4.4 | 0.192 | 0.103 |
| telescope102 | 163.7 | 3.4 | 0.214 | 0.105 |

##### In sample vs out of sample

| metric | in sample | out of sample |
| --- | --- | --- |
| payload_dyn, shape Monitor: detected | 0/5 | 0/10 |
| payload_dyn, shape Monitor: median motions to detect | n/a | n/a |
| payload_dyn, shape Monitor: false alarms before damage, per run | 0/5 runs | 0/10 runs |
| payload_dyn, DynamicsMonitor: detected | 4/5 | 4/10 |
| payload_dyn, DynamicsMonitor: median motions to detect | 13.0 | 11.0 |
| payload_dyn, DynamicsMonitor: false alarms before damage, per run | 0/5 runs | 0/10 runs |
| payload_dyn, DynamicsMonitor: cause named right | 4/5 | 4/10 |
| payload_dyn, DynamicsMonitor: added payload within 0.1 kg | 3/5 | 3/10 |
| weak_motor, shape Monitor: detected | 0/5 | 0/10 |
| weak_motor, shape Monitor: median motions to detect | n/a | n/a |
| weak_motor, shape Monitor: false alarms before damage, per run | 0/5 runs | 0/10 runs |
| weak_motor, DynamicsMonitor: detected | 2/5 | 4/10 |
| weak_motor, DynamicsMonitor: median motions to detect | 15.0 | 21.0 |
| weak_motor, DynamicsMonitor: false alarms before damage, per run | 0/5 runs | 0/10 runs |
| weak_motor, DynamicsMonitor: cause named right | 2/5 | 4/10 |

##### Undamaged runs: false alarms over the whole run

Nothing is damaged; the run continues 40 motions past motion 48 exactly like a damaged run. Every alarm is false.

| body | shape Monitor alarms | DynamicsMonitor alarms | motions watched |
| --- | --- | --- | --- |
| arm106 | 0 | 0 | 91.0 |
| arm107 | 0 | 0 | 95.0 |
| scara104 | 0 | 0 | 92.0 |
| scara105 | 0 | 0 | 89.0 |
| telescope103 | 0 | 0 | 91.0 |

##### What got worse out of sample

- payload_dyn, DynamicsMonitor: detected: 4/5 in sample, 4/10 out of sample
- payload_dyn, DynamicsMonitor: cause named right: 4/5 in sample, 4/10 out of sample
- payload_dyn, DynamicsMonitor: added payload within 0.1 kg: 3/5 in sample, 3/10 out of sample
- weak_motor, DynamicsMonitor: median motions to detect: 15.0 in sample, 21.0 out of sample

#### With LLM hypothesizers

Same bodies, seeds, budgets and monitor settings as above; the only difference is that one LLM hypothesizer per provider with an API key joins every swarm. LLM answers vary, so these runs are not deterministic: rerunning gives somewhat different numbers.

##### In sample, LLM on

Bodies: arm1, arm2, arm3, scara1, scara2. LLM hypothesizers: on (hyp-claude, hyp-gemini); 77 LLM hypotheses posted across 20 runs. Runs are not deterministic.

###### Detection

| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |
| --- | --- | --- | --- | --- | --- | --- |
| payload_dyn | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| payload_dyn | DynamicsMonitor | 3/5 | 9.0 | 0 | 3/5 | 2/5 |
| weak_motor | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| weak_motor | DynamicsMonitor | 1/5 | 17.0 | 0 | 1/5 | n/a |

###### Every run

| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm1 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm1 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm1 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm1 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm2 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm2 | 350 g payload in the gripper (dynamic) | dynamics | 17.0 | payload | 0.307 | n/a | 0 |
| arm2 | motor 4 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm2 | motor 4 lost half its stiffness | dynamics | 17.0 | weak motor 4 (truth 4) | n/a | 0.52 | 0 |
| arm3 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm3 | 350 g payload in the gripper (dynamic) | dynamics | 9.0 | payload | 0.789 | n/a | 0 |
| arm3 | motor 4 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm3 | motor 4 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara1 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara1 | 350 g payload in the gripper (dynamic) | dynamics | 5.0 | payload | 0.350 | n/a | 0 |
| scara1 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara1 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara2 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara2 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara2 | motor 3 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara2 | motor 3 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |

###### Tip path error on fast moves, before damage (vs noise free truth)

| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |
| --- | --- | --- | --- | --- |
| arm1 | 234.4 | 3.7 | 0.312 | 0.309 |
| arm2 | 265.7 | 8.0 | 0.183 | 0.207 |
| arm3 | 266.0 | 14.7 | 0.702 | 0.205 |
| scara1 | 177.9 | 3.3 | 0.235 | 0.309 |
| scara2 | 124.8 | 2.5 | 0.251 | 0.207 |

##### Out of sample, LLM on

Bodies: arm101, arm102, arm103, arm104, arm105, scara101, scara102, scara103, telescope101, telescope102. LLM hypothesizers: on (hyp-claude, hyp-gemini); 195 LLM hypotheses posted across 50 runs. Runs are not deterministic.

###### Detection

| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |
| --- | --- | --- | --- | --- | --- | --- |
| payload_dyn | shape Monitor | 0/10 | n/a | 0 | does not name causes | n/a |
| payload_dyn | DynamicsMonitor | 6/10 | 15.0 | 0 | 6/10 | 5/10 |
| weak_motor | shape Monitor | 0/10 | n/a | 0 | does not name causes | n/a |
| weak_motor | DynamicsMonitor | 6/10 | 15.0 | 0 | 6/10 | n/a |

###### Every run

| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm102 | 350 g payload in the gripper (dynamic) | dynamics | 25.0 | payload | 0.362 | n/a | 0 |
| arm102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm102 | motor 2 lost half its stiffness | dynamics | 25.0 | weak motor 2 (truth 2) | n/a | 0.51 | 0 |
| arm103 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm103 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.283 | n/a | 0 |
| arm103 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm103 | motor 2 lost half its stiffness | dynamics | 1.0 | weak motor 2 (truth 2) | n/a | 0.43 | 0 |
| arm104 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm104 | 350 g payload in the gripper (dynamic) | dynamics | 17.0 | payload | 0.314 | n/a | 0 |
| arm104 | motor 3 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm104 | motor 3 lost half its stiffness | dynamics | 17.0 | weak motor 3 (truth 3) | n/a | 0.50 | 0 |
| arm105 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm105 | 350 g payload in the gripper (dynamic) | dynamics | 13.0 | payload | 0.323 | n/a | 0 |
| arm105 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm105 | motor 1 lost half its stiffness | dynamics | 13.0 | weak motor 1 (truth 1) | n/a | 0.49 | 0 |
| scara101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara102 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.326 | n/a | 0 |
| scara102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara102 | motor 2 lost half its stiffness | dynamics | 1.0 | weak motor 2 (truth 2) | n/a | 0.48 | 0 |
| scara103 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara103 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara103 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara103 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| telescope101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| telescope101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| telescope102 | 350 g payload in the gripper (dynamic) | dynamics | 25.0 | payload | 0.451 | n/a | 0 |
| telescope102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| telescope102 | motor 2 lost half its stiffness | dynamics | 25.0 | weak motor 2 (truth 2) | n/a | 0.48 | 0 |

###### Tip path error on fast moves, before damage (vs noise free truth)

| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |
| --- | --- | --- | --- | --- |
| arm101 | 33.8 | 2.6 | 0.065 | 0.103 |
| arm102 | 182.2 | 6.0 | 0.147 | 0.105 |
| arm103 | 212.9 | 5.2 | 0.097 | 0.066 |
| arm104 | 259.8 | 7.2 | 0.231 | 0.187 |
| arm105 | 91.4 | 2.1 | 0.348 | 0.353 |
| scara101 | 140.0 | 2.5 | 0.169 | 0.103 |
| scara102 | 137.7 | 1.8 | 0.109 | 0.105 |
| scara103 | 167.2 | 3.3 | 0.026 | 0.066 |
| telescope101 | 127.4 | 4.8 | 0.208 | 0.103 |
| telescope102 | 163.9 | 3.9 | 0.192 | 0.105 |

##### LLM off vs LLM on

| metric | in sample: off | in sample: on | out of sample: off | out of sample: on |
| --- | --- | --- | --- | --- |
| payload_dyn, shape Monitor: detected | 0/5 | 0/5 | 0/10 | 0/10 |
| payload_dyn, shape Monitor: median motions to detect | n/a | n/a | n/a | n/a |
| payload_dyn, shape Monitor: false alarms before damage | 0/5 runs | 0/5 runs | 0/10 runs | 0/10 runs |
| payload_dyn, DynamicsMonitor: detected | 4/5 | 3/5 | 4/10 | 6/10 |
| payload_dyn, DynamicsMonitor: median motions to detect | 13.0 | 9.0 | 11.0 | 15.0 |
| payload_dyn, DynamicsMonitor: false alarms before damage | 0/5 runs | 0/5 runs | 0/10 runs | 0/10 runs |
| payload_dyn, DynamicsMonitor: cause named right | 4/5 | 3/5 | 4/10 | 6/10 |
| payload_dyn, DynamicsMonitor: added payload within 0.1 kg | 3/5 | 2/5 | 3/10 | 5/10 |
| weak_motor, shape Monitor: detected | 0/5 | 0/5 | 0/10 | 0/10 |
| weak_motor, shape Monitor: median motions to detect | n/a | n/a | n/a | n/a |
| weak_motor, shape Monitor: false alarms before damage | 0/5 runs | 0/5 runs | 0/10 runs | 0/10 runs |
| weak_motor, DynamicsMonitor: detected | 2/5 | 1/5 | 4/10 | 6/10 |
| weak_motor, DynamicsMonitor: median motions to detect | 15.0 | 17.0 | 21.0 | 15.0 |
| weak_motor, DynamicsMonitor: false alarms before damage | 0/5 runs | 0/5 runs | 0/10 runs | 0/10 runs |
| weak_motor, DynamicsMonitor: cause named right | 2/5 | 1/5 | 4/10 | 6/10 |
| shape Monitor: alarms on undamaged bodies |  |  | 0/5 runs | 0/5 runs |
| DynamicsMonitor: alarms on undamaged bodies |  |  | 0/5 runs | 0/5 runs |

##### Where LLMs made it worse

- in sample, payload_dyn, DynamicsMonitor: detected: 4/5 with LLMs off, 3/5 with LLMs on
- out of sample, payload_dyn, DynamicsMonitor: median motions to detect: 11.0 with LLMs off, 15.0 with LLMs on
- in sample, payload_dyn, DynamicsMonitor: cause named right: 4/5 with LLMs off, 3/5 with LLMs on
- in sample, payload_dyn, DynamicsMonitor: added payload within 0.1 kg: 3/5 with LLMs off, 2/5 with LLMs on
- in sample, weak_motor, DynamicsMonitor: detected: 2/5 with LLMs off, 1/5 with LLMs on
- in sample, weak_motor, DynamicsMonitor: median motions to detect: 15.0 with LLMs off, 17.0 with LLMs on
- in sample, weak_motor, DynamicsMonitor: cause named right: 2/5 with LLMs off, 1/5 with LLMs on

Notes: the swarm gets one absolute reference, the servo datasheet (rotor inertia and velocity gain). Without it a payload in kilograms is unobservable from positions: scaling every mass, kp and damping together leaves every path unchanged. The added payload is estimated by refitting only the payload on the two sentinel trajectories that raised the alarm.

Tuning disclosure: the DynamicsMonitor's settings were changed once after a first run on the in sample bodies. That run used a median baseline, a 2x / +6 mm threshold and a 10 mm kinematic gate, and detected 4/10. The fixes: a baseline that one post damage sentinel cannot inflate (a real bug: arm2's 8 to 91 mm payload jump was missed), a threshold of max(1.5x, +2.5 mm), and a 15 mm kinematic gate (arm3's shape model sat at 11 mm, so it never fitted dynamics). The shape Monitor was not changed. The in sample numbers are in sample; the out of sample section is the honest test.

## 13. Vision

Source: `results/summary_vision.md`, last changed in 201e824 on 2026-11-01. Camera perception only; independent of the swarm version.

### Vision: two cameras instead of a marker

#### Detector 1: red tip sphere, two fixed cameras (V1)

Two fixed cameras (front at (2.0, 0.0, 0.85) m, fovy 50.0 deg, side at (0.0, -2.0, 0.85) m, fovy 50.0 deg), 640x480, rendered with EGL on NVIDIA H200/PCIe/SSE2. Camera matrices come from the MuJoCo camera parameters only. Per family: 5 bodies x 40 random poses. Error is the distance between the triangulated and the true rendered tip.

| family | poses | detected in both views | hidden (in view, covered) | out of view | median error, mm | 90th percentile, mm | median pixel error | median ray gap, mm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arm | 200 | 189 (94%) | 11 (6%) | 0 (0%) | 3.7 | 6.9 | 0.67 | 1.3 |
| gantry | 200 | 200 (100%) | 0 (0%) | 0 (0%) | 3.0 | 6.5 | 0.32 | 0.6 |
| scara | 200 | 194 (97%) | 6 (3%) | 0 (0%) | 4.3 | 6.9 | 0.35 | 0.8 |
| telescope | 200 | 193 (96%) | 7 (4%) | 0 (0%) | 3.1 | 6.6 | 0.55 | 1.1 |

Hidden and out of view poses return NaN instead of a guess. For comparison, the marker robot's simulated camera noise is 2 mm per axis (about 3.5 mm as a 3D distance).

Detector note: the colour rule was changed once before this run, after a check on 110 views of other poses showed brightness weighting biased the centroid about 0.9 px upward (overhead light shades the lower half of the sphere).

#### Detector 2: no marker, Gemini Robotics ER (V2)

Same 200 poses per family as above. Markerless: the tip sphere is painted like the links. Gemini (`models/gemini-robotics-er-2-preview`, temperature 0) is asked to point to the end of the robot's last link in each view; its normalized [y, x] point is triangulated as before. 1600 images, 1600 real calls this run (answers are cached by image hash, so reruns are free), 0 call errors. "Bad disagreement" = the two views' rays miss each other by more than 20 mm.

| family | poses | colour marker: located | colour: median / p90, mm | Gemini markerless: located | Gemini: median / p90, mm | Gemini views disagree badly (> 20 mm) | Gemini median pixel error |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm | 200 | 189 (94%) | 3.7 / 6.9 | 200 (100%) | 6.3 / 25.7 | 22 of 200 (11%) | 1.4 |
| gantry | 200 | 200 (100%) | 3.0 / 6.5 | 200 (100%) | 6.7 / 15.3 | 18 of 200 (9%) | 1.3 |
| scara | 200 | 194 (97%) | 4.3 / 6.9 | 200 (100%) | 189.9 / 293.7 | 60 of 200 (30%) | 22.0 |
| telescope | 200 | 193 (96%) | 3.1 / 6.6 | 200 (100%) | 6.3 / 14.4 | 13 of 200 (6%) | 1.4 |

Located = a point in both views (Gemini: it answered with a point in both; colour: the red sphere was visible in both). Markerless mode has no fallback; the colour detector is only a fallback in marker mode.

#### Making markerless precise (V5)

Same 200 poses per family as above, markerless, image only (no robot geometry). Each cell: median / 90th percentile error (mm) on accepted readings, then readings accepted (a reading is rejected when its views' rays miss by more than 20 mm, exactly as CameraRobot does).

| detector | arm | gantry | scara | telescope |
| --- | --- | --- | --- | --- |
| red marker, 2 cameras (V1, reference) | 3.7 / 6.9 (189/200) | 3.0 / 6.5 (200/200) | 4.3 / 6.9 (194/200) | 3.1 / 6.6 (193/200) |
| A: Gemini points once per view (the V2 detector) | 6.0 / 9.2 (178/200) | 6.4 / 11.9 (182/200) | 201.2 / 302.5 (140/200) | 6.1 / 9.5 (187/200) |
| B: A + snap to the link's end cap in the image | 2.0 / 8.7 (177/200) | 5.8 / 15.0 (182/200) | 201.3 / 302.8 (139/200) | 1.9 / 6.2 (184/200) |
| C: zoom: ask again on a 4x close-up, then snap | 2.0 / 8.8 (175/200) | 4.2 / 16.8 (154/200) | 161.7 / 302.7 (112/200) | 1.9 / 22.7 (153/200) |
| D: ask for 3 candidates per view, keep the pair that agrees | 2.3 / 423.0 (193/200) | 6.6 / 16.5 (190/200) | 212.9 / 313.6 (189/200) | 2.4 / 309.2 (192/200) |
| E (A): 4 cameras, 1280x960, Gemini points once | 5.1 / 7.9 (198/200) | 5.1 / 7.7 (200/200) | 205.6 / 303.2 (195/200) | 5.1 / 7.7 (198/200) |
| E (B): 4 cameras, 1280x960, point + snap, one disagreeing view dropped | 1.3 / 5.9 (197/200) | 3.0 / 7.6 (200/200) | 206.5 / 308.8 (192/200) | 1.2 / 4.9 (199/200) |
| E (B strict): 4 cameras, 1280x960, point + snap, every view must agree (the improved detector) | 1.3 / 3.5 (147/200) | 3.7 / 7.3 (109/200) | 251.6 / 318.6 (41/200) | 1.1 / 3.4 (152/200) |
| E (F): 4 cameras, walk the robot's pixels from the mount to the chain's end (no Gemini) | 1.3 / 8.8 (199/200) | 172.3 / 258.9 (195/200) | 14.7 / 176.5 (192/200) | 5.6 / 261.0 (198/200) |
| E (G): 4 cameras, Gemini+snap or chain end per view, the combination that agrees | 1.3 / 4.8 (200/200) | 6.0 / 231.0 (200/200) | 164.7 / 290.4 (200/200) | 1.1 / 220.4 (200/200) |

What this shows:

- Snapping Gemini's point to the end cap of the link (B) cuts the median pixel error from 1.5 to 0.6 px and the arm and telescope medians from about 6 mm to 2 mm, better than the red marker, at no extra cost.
- Four cameras at 1280x960 with the snap (E (B)) match or beat the red marker on arms, gantries and telescopes on these poses, with almost every reading accepted. Inside the swarm, though, dropping one disagreeing view let through rare readings that were hundreds of mm off (all remaining views agreeing on a wrong point), and a least squares fit cannot survive those. Requiring every view to agree (E (B strict)) accepts fewer readings but keeps them clean; it is what the swarm runs below use. This rule was chosen after inspecting two swarm runs (arm seed 2, telescope seed 1), so it is partly in sample.
- SCARA is not solved: Gemini consistently points at the top of the vertical shaft in every view, so more views agree on the wrong place. Walking the robot's pixels to the chain's end (E (F)) finds the SCARA tip (median 14.7 mm) but breaks on gantries and telescopes, where links overlap in the image; no rule tried here combines the two without tuning per body type (E (G)).
- Zoom re-queries (C) and candidate lists (D) did not help: C rejects more readings, D sometimes pairs wrong candidates (90th percentiles of 300 to 400 mm).
- Disclosure: the snap's distance cap (one cap diameter) was chosen after looking at failures on these same poses; the swarm runs below use fresh motions and act as the independent check.

#### Telling the camera what it is looking at: SCARA (V6)

SCARA is where markerless fails: Gemini points at the top of the vertical shaft. Same 200 SCARA poses, markerless, every point snapped to the link's end cap; median / 90th percentile error on accepted readings (accepted out of 200). The structure-informed question uses the TRUE structure here, standing in for what the swarm discovers (an upper bound for the feedback loop below).

| question to Gemini, 2 cameras 640x480 | SCARA |
| --- | --- |
| "point to the tip" (V2 question) | 201.3 / 302.8 (139/200) |
| "point to the end effector, where a tool is mounted" | 224.3 / 303.1 (124/200) |
| "follow the links from the base to the free end" | 224.8 / 312.3 (122/200) |
| structure-informed: the body's joint list, then "point to the end of the last link" | 61.3 / 299.1 (139/200) |

Active perception, no Gemini: nudge each channel in turn; the robot pixels that change under every nudge are the last link; its tip end is where the most distal channel's sweep concentrates (2 cameras, all families, n_channels + 1 renders per reading, so a calibration tool on a real robot):

| | arm | gantry | scara | telescope |
| --- | --- | --- | --- | --- |
| motion only, 2 cameras | 24.7 / 87.7 (149/200) | 12.3 / 68.4 (164/200) | 12.6 / 30.3 (173/200) | 46.6 / 88.6 (157/200) |

| 4 cameras 1280x960 | SCARA |
| --- | --- |
| structure-informed Gemini + snap, drop 1 | 85.6 / 291.9 (194/200) |
| chain end walk, drop 1 | 14.7 / 176.5 (192/200) |
| either, agreeing combination, drop 1 | 127.0 / 269.2 (200/200) |
| structure-informed Gemini + snap, strict | 7.1 / 288.7 (49/200) |
| chain end walk, strict | 136.6 / 194.5 (52/200) |
| either, agreeing combination, strict | 9.3 / 238.0 (98/200) |

What this shows: generic rewordings do not help. Telling Gemini the body's structure cuts the median from about 200 mm to 61 mm (2 cameras), and to 7 mm when all 4 views must agree, but a minority of readings are wrong in the same way in every view, so no geometric check removes them and the 90th percentile stays near 300 mm. Walking the robot's pixels to the chain's end finds the tip more often (median 14.7 mm) but has its own tail. Active perception (what moves when every joint moves) gives the best SCARA tail by far (median 12.6, 90th percentile 30 mm, against about 300 mm for every Gemini question) but is worse than Gemini on arms and telescopes; it costs extra motions per reading. SCARA is therefore much better located than before but not at marker level, and no single detector is best for every body.

Feedback loop at swarm level (condition "improved + gaze feedback loop" below): a GazeAgent turns the swarm's discovered structure into the camera's question and opens a new epoch so earlier readings stop counting. It made learning WORSE: each switch restarts learning and the 64 motion budget ran out before a new model (telescopes: no model, against 5.1 and 10.7 mm without it); on gantries it sometimes steered by a wrong structure; on SCARA it never fired because too many readings were rejected for the channel agents to finish. A second design keeps everything learned and switches the camera's question once (condition "improved + gaze, keep data, 1 switch"): it fixes that failure and matches or beats the same camera setup without the loop (median reach error, keep-data loop vs no loop: arm 5.3 vs 5.3 mm, telescope 5.4 vs 7.9 mm, gantry 22.3 vs 27.7 mm with the structure still wrong; SCARA still no model). A modest gain on 2 seeds, and the second design was chosen after seeing the first fail.

#### Swarm learns from cameras (V3)

Unknown body mode, 2 seeds per family, budget 64 motions, same swarm and scorer in every condition; reach error and structure are scored on the true tip. Camera readings whose views disagree (rays > 20 mm apart) or that miss the tip are rejected as bad observations, never as body changes.

| family | condition | structure found | median reach error, mm | bad observations (of motions) | Monitor alarms |
| --- | --- | --- | --- | --- | --- |
| arm | marker (no camera) | 2/2 | 1.7 | 0 of 140 | 0 |
| arm | two cameras, red marker | 2/2 | 3.8 | 30 of 140 | 0 |
| arm | two cameras, no marker (Gemini) | 1/2 | 158.5 | 33 of 140 | 0 |
| arm | 4 cameras, no marker, improved, drop 1 view | 2/2 | 59.3 | 2 of 134 | 0 |
| arm | 4 cameras, no marker, improved, all views agree | 2/2 | 5.3 | 44 of 139 | 0 |
| arm | no marker, improved + gaze feedback loop | 1/2 | 6.5 | 24 of 129 | 0 |
| arm | no marker, improved + gaze, keep data, 1 switch | 2/2 | 5.3 | 52 of 135 | 0 |
| gantry | marker (no camera) | 2/2 | 1.1 | 0 of 128 | 0 |
| gantry | two cameras, red marker | 2/2 | 3.3 | 0 of 128 | 0 |
| gantry | two cameras, no marker (Gemini) | 2/2 | 7.6 | 7 of 136 | 0 |
| gantry | 4 cameras, no marker, improved, drop 1 view | 2/2 | 4.5 | 0 of 128 | 0 |
| gantry | 4 cameras, no marker, improved, all views agree | 0/2 | 27.7 | 28 of 136 | 0 |
| gantry | no marker, improved + gaze feedback loop | 0/2 | n/a | 36 of 128 | 0 |
| gantry | no marker, improved + gaze, keep data, 1 switch | 0/2 | 22.3 | 38 of 136 | 0 |
| scara | marker (no camera) | 2/2 | 1.3 | 0 of 128 | 0 |
| scara | two cameras, red marker | 2/2 | 3.3 | 7 of 128 | 0 |
| scara | two cameras, no marker (Gemini) | 0/2 | 101.1 | 45 of 136 | 0 |
| scara | 4 cameras, no marker, improved, drop 1 view | 0/2 | 100.5 | 6 of 136 | 0 |
| scara | 4 cameras, no marker, improved, all views agree | 0/2 | n/a | 121 of 132 | 0 |
| scara | no marker, improved + gaze feedback loop | 0/2 | n/a | 121 of 132 | 0 |
| scara | no marker, improved + gaze, keep data, 1 switch | 0/2 | n/a | 121 of 132 | 0 |
| telescope | marker (no camera) | 2/2 | 1.0 | 0 of 130 | 0 |
| telescope | two cameras, red marker | 2/2 | 3.2 | 19 of 130 | 0 |
| telescope | two cameras, no marker (Gemini) | 2/2 | 9.3 | 36 of 136 | 0 |
| telescope | 4 cameras, no marker, improved, drop 1 view | 2/2 | 13.5 | 5 of 136 | 0 |
| telescope | 4 cameras, no marker, improved, all views agree | 2/2 | 7.9 | 51 of 130 | 0 |
| telescope | no marker, improved + gaze feedback loop | 0/2 | n/a | 24 of 128 | 0 |
| telescope | no marker, improved + gaze, keep data, 1 switch | 2/2 | 5.4 | 55 of 134 | 0 |

##### Where camera input makes things worse

- arm, two cameras, red marker: median reach error 3.8 mm vs 1.7 mm with the marker
- arm, two cameras, no marker (Gemini): structure found 1/2 vs 2/2 with the marker
- arm, two cameras, no marker (Gemini): median reach error 158.5 mm vs 1.7 mm with the marker
- arm, 4 cameras, no marker, improved, drop 1 view: median reach error 59.3 mm vs 1.7 mm with the marker
- arm, 4 cameras, no marker, improved, all views agree: median reach error 5.3 mm vs 1.7 mm with the marker
- arm, no marker, improved + gaze feedback loop: structure found 1/2 vs 2/2 with the marker
- arm, no marker, improved + gaze feedback loop: median reach error 6.5 mm vs 1.7 mm with the marker
- arm, no marker, improved + gaze, keep data, 1 switch: median reach error 5.3 mm vs 1.7 mm with the marker
- gantry, two cameras, red marker: median reach error 3.3 mm vs 1.1 mm with the marker
- gantry, two cameras, no marker (Gemini): median reach error 7.6 mm vs 1.1 mm with the marker
- gantry, 4 cameras, no marker, improved, drop 1 view: median reach error 4.5 mm vs 1.1 mm with the marker
- gantry, 4 cameras, no marker, improved, all views agree: structure found 0/2 vs 2/2 with the marker
- gantry, 4 cameras, no marker, improved, all views agree: median reach error 27.7 mm vs 1.1 mm with the marker
- gantry, no marker, improved + gaze feedback loop: structure found 0/2 vs 2/2 with the marker
- gantry, no marker, improved + gaze feedback loop: no model by the end of the budget (marker: 1.1 mm)
- gantry, no marker, improved + gaze, keep data, 1 switch: structure found 0/2 vs 2/2 with the marker
- gantry, no marker, improved + gaze, keep data, 1 switch: median reach error 22.3 mm vs 1.1 mm with the marker
- scara, two cameras, red marker: median reach error 3.3 mm vs 1.3 mm with the marker
- scara, two cameras, no marker (Gemini): structure found 0/2 vs 2/2 with the marker
- scara, two cameras, no marker (Gemini): median reach error 101.1 mm vs 1.3 mm with the marker
- scara, 4 cameras, no marker, improved, drop 1 view: structure found 0/2 vs 2/2 with the marker
- scara, 4 cameras, no marker, improved, drop 1 view: median reach error 100.5 mm vs 1.3 mm with the marker
- scara, 4 cameras, no marker, improved, all views agree: structure found 0/2 vs 2/2 with the marker
- scara, 4 cameras, no marker, improved, all views agree: no model by the end of the budget (marker: 1.3 mm)
- scara, no marker, improved + gaze feedback loop: structure found 0/2 vs 2/2 with the marker
- scara, no marker, improved + gaze feedback loop: no model by the end of the budget (marker: 1.3 mm)
- scara, no marker, improved + gaze, keep data, 1 switch: structure found 0/2 vs 2/2 with the marker
- scara, no marker, improved + gaze, keep data, 1 switch: no model by the end of the budget (marker: 1.3 mm)
- telescope, two cameras, red marker: median reach error 3.2 mm vs 1.0 mm with the marker
- telescope, two cameras, no marker (Gemini): median reach error 9.3 mm vs 1.0 mm with the marker
- telescope, 4 cameras, no marker, improved, drop 1 view: median reach error 13.5 mm vs 1.0 mm with the marker
- telescope, 4 cameras, no marker, improved, all views agree: median reach error 7.9 mm vs 1.0 mm with the marker
- telescope, no marker, improved + gaze feedback loop: structure found 0/2 vs 2/2 with the marker
- telescope, no marker, improved + gaze feedback loop: no model by the end of the budget (marker: 1.0 mm)
- telescope, no marker, improved + gaze, keep data, 1 switch: median reach error 5.4 mm vs 1.0 mm with the marker

Notes: a camera reading that is rejected still costs its motion. A rejected reading resets the stock Monitor's strike count (its NaN surprise is never above threshold), which can delay a real alarm by one sentinel. LLM hypothesizers are off in every condition so the only model in the loop is the detector.

## Failures we found

Numbers are reach error in mm, median [95% CI] n. Every setting where the swarm misses (wrong structure in some run, damage not noticed, a false alarm, or a median over 10 mm) or a baseline's median beats the swarm's. Rows per family are included for faults and noise.

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

## Ties

Pooled settings where a baseline's median is not better than the swarm's but its 95% interval overlaps the swarm's: the data cannot tell them apart.

| experiment | setting | what happened | numbers |
| --- | --- | --- | --- |
| bodies, independent seeds 101 to 105 | all | pipeline ties the swarm | 1.7 [1.0 to 2.0] n=20 vs swarm 1.5 [1.4 to 1.9] n=20 |
| damage | bent_axis | single_probe ties the swarm | 7.3 [6.3 to 8.8] n=20 vs swarm 2.3 [1.6 to 7.1] n=20, 10 no model |
| damage | bent_axis | pipeline ties the swarm | 2.4 [1.9 to 4.6] n=20, 4 no model vs swarm 2.3 [1.6 to 7.1] n=20, 10 no model |
| damage | locked_joint | pipeline ties the swarm | 2.2 [2.0 to 2.6] n=20, 3 no model vs swarm 1.7 [1.3 to 2.4] n=20, 12 no model |
| damage | long_link | pipeline ties the swarm | 2.4 [1.9 to 2.7] n=20 vs swarm 1.3 [1.0 to 2.8] n=20, 13 no model |
| damage | reversed_motor | pipeline ties the swarm | 2.0 [1.5 to 2.5] n=20, 1 no model vs swarm 1.6 [0.9 to 2.0] n=20, 13 no model |
| damage | tool | pipeline ties the swarm | 2.4 [2.1 to 2.9] n=20 vs swarm 1.8 [1.5 to 2.5] n=20, 12 no model |
| faults, original seeds 1 to 5 | none | pipeline ties the swarm | 1.8 [1.4 to 2.1] n=20 vs swarm 1.7 [1.3 to 2.0] n=20 |
| faults, original seeds 1 to 5 | bad_llm | single_probe ties the swarm | 1.5 [1.2 to 1.7] n=20 vs swarm 1.5 [1.3 to 1.9] n=20 |
| faults, independent seeds 101 to 105 | none | pipeline ties the swarm | 1.7 [1.0 to 2.0] n=20 vs swarm 1.5 [1.4 to 1.9] n=20 |
| faults, independent seeds 101 to 105 | modeler_crash | pipeline ties the swarm | 2.4 [1.8 to 3.0] n=20, 18 no model vs swarm 1.7 [1.4 to 2.2] n=20 |
| noise | 1 | single_probe ties the swarm | 1.1 [0.9 to 1.3] n=20 vs swarm 1.0 [0.8 to 1.3] n=20 |
| noise | 1 | pipeline ties the swarm | 1.1 [0.9 to 1.5] n=20 vs swarm 1.0 [0.8 to 1.3] n=20 |
| noise | 2 | pipeline ties the swarm | 1.8 [1.4 to 2.1] n=20 vs swarm 1.7 [1.3 to 2.0] n=20 |
| learning | 16 motions | mlp ties the swarm | 308.2 [192.4 to 398.0] n=10 vs swarm 196.9 [8.5 to 351.5] n=10, 4 no model |

## Why a baseline ties or beats the swarm

- **bodies**: Every structure is found by swarm, single_probe and pipeline alike (100% on both seed sets), so the difference is reach error, and the intervals overlap except single_probe on gantry. The swarm spends 32 to 40 of its 64 motions on single channel sweeps (home and bent pose for every channel, plus review rechecks) where single_probe and the pipeline spend 16, so it fits on fewer mixed motions. Those extra sweeps buy robustness to one bad finding (fault table), not accuracy on a clean body.
- **damage**: After an alarm the swarm starts a new epoch and sweeps every channel again from two poses (median 68 probe motions per damage run vs 32 for the pipeline), so at motion 128 it has no trusted model in 10 to 13 of 20 runs for the kinds it detects, and its recovered error medians cover only the runs that re-crowned a model. Payload changes the tip too little to trip the monitor (swarm 1 of 20, pipeline 0 of 20); single_probe never looks for damage and simply keeps fitting, which on such a small change costs it nothing.
- **faults**: Under no fault and bad_llm the swarm pays the same extra sweeps as on clean bodies (single_probe has no slot for the bad source, so bad_llm cannot touch it). noisy_channel is the one fault the swarm does not handle: single_probe and the pipeline end closer (3.0 to 3.7 mm vs 5.1 to 5.5 mm). Likely cause, not separately tested: the camera noise corrupts every sweep of that channel from any pose, so the swarm's second and third sweeps put 8 to 12 noisy observations into its training data where the baselines usually put 4, and replication cannot outvote a sensor that is wrong every time.
- **noise**: At 1 to 5 mm of camera noise the baselines that probe channels end slightly closer, the same extra sweep cost as on clean bodies (intervals overlap at every pooled level). At 10 mm the swarm ends closest of the four (9.1 mm vs 31 to 50 mm) but still gets 7 of 20 structures wrong.
- **learning**: On known arms (no structure to discover) the single agent fits every motion with one chain model from the first batch; the swarm holds every fourth motion out for validation and crowns a model only when both validators agree, so early on it has no model or a model fit on fewer motions.
