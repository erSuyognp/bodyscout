# BodyScout results summary

## Learning an unknown body (4 arms, median [IQR] reach error, mm)

| motions | BodyScout swarm | Single agent (chain model) | Single agent (neural net) |
| --- | --- | --- | --- |
| 8 | no model yet | 30.6 [13.0 to 99.0] | no model yet |
| 12 | no model yet | 5.9 [5.0 to 6.3] | no model yet |
| 16 | 306.6 [306.6 to 306.6] | 4.2 [3.5 to 5.0] | 362.7 [307.2 to 400.5] |
| 24 | 4.6 [3.9 to 80.2] | 2.8 [2.6 to 2.9] | 234.1 [190.7 to 292.4] |
| 32 | 3.5 [2.6 to 4.7] | 2.6 [2.2 to 2.9] | 130.2 [116.0 to 215.7] |
| 48 | 2.2 [1.5 to 3.0] | 2.1 [1.4 to 2.7] | 118.6 [104.0 to 163.7] |
| 64 | 2.0 [1.5 to 2.7] | 1.4 [1.0 to 2.1] | 163.0 [143.7 to 178.8] |

## Damage mid run (break at motion 48)

| damage | swarm detected at (median motions after damage) | swarm error at end, mm | single agent error at end, mm |
| --- | --- | --- | --- |
| bent_axis | 33.5 (2/3 runs) | 2.5 | 7.2 |
| long_link | 20.0 (3/3 runs) | 2.8 | 24.8 |
| reversed_motor | 20.0 (3/3 runs) | 2.9 | 43.5 |
| tool | 20.0 (3/3 runs) | 2.7 | 31.3 |

Gaps in the swarm curve are deliberate: between the alarm and the next crowned model the planner has no trusted model and refuses to move.

## Knowing when it is guessing

| targets | BodyScout refused | naive planner median miss, mm |
| --- | --- | --- |
| reachable | 0% | 2 |
| out of reach | 100% | 326 |

## Unknown body types (median reach error at 64 motions, mm; structure found)

| body | swarm | single agent | swarm structure right | single structure right |
| --- | --- | --- | --- | --- |
| arm | 2.5 | 213.8 | 3/3 | 1/3 |
| gantry | 1.1 | 46.8 | 3/3 | 1/3 |
| scara | 1.7 | 38.0 | 3/3 | 1/3 |
| telescope | 1.7 | 47.6 | 3/3 | 1/3 |

# Dynamics change detection

Damage at motion 48: payload_dyn (+0.35 kg at the tip) or weak_motor (one joint, kp x 0.5). Bodies: arm1, arm2, arm3, scara1, scara2 (body type unknown to the swarm). Watch window after damage: 40 motions. Identical swarms; only the monitor differs. A shape sentinel costs 1 motion, a dynamics sentinel (25 samples at 10 ms) costs 0.5.

## Detection

| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |
| --- | --- | --- | --- | --- | --- | --- |
| payload_dyn | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| payload_dyn | DynamicsMonitor | 4/5 | 13.0 | 0 | 4/5 | 3/5 |
| weak_motor | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| weak_motor | DynamicsMonitor | 2/5 | 15.0 | 0 | 2/5 | n/a |

## Every run

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

## Tip path error on fast moves, before damage (vs noise free truth)

| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |
| --- | --- | --- | --- | --- |
| arm1 | 234.6 | 6.5 | 0.400 | 0.309 |
| arm2 | 265.4 | 7.5 | 0.199 | 0.207 |
| arm3 | 265.9 | 14.4 | 0.642 | 0.205 |
| scara1 | 177.4 | 4.3 | 0.277 | 0.309 |
| scara2 | 124.9 | 2.0 | 0.207 | 0.207 |

Notes: the swarm gets one absolute reference, the servo datasheet (rotor inertia and velocity gain). Without it a payload in kilograms is unobservable from positions: scaling every mass, kp and damping together leaves every path unchanged. The added payload is estimated by refitting only the payload on the two sentinel trajectories that raised the alarm.

Tuning disclosure: the DynamicsMonitor's settings were changed once after a first run on these same 10 bodies. That run used a median baseline, a 2x / +6 mm threshold and a 10 mm kinematic gate, and detected 4/10. The fixes: a baseline that one post damage sentinel cannot inflate (a real bug: arm2's 8 to 91 mm payload jump was missed), a threshold of max(1.5x, +2.5 mm), and a 15 mm kinematic gate (arm3's shape model sat at 11 mm, so it never fitted dynamics). The shape Monitor was not changed. Treat these numbers as in sample.
