# BodyScout results summary

Cells are median reach error in mm [bootstrap 95% CI of the median, 2000 resamples] over runs.

## Learning an unknown body (10 arms, median reach error [95% CI], mm)

| motions | BodyScout swarm | Single agent (chain model) | Single agent (neural net) |
| --- | --- | --- | --- |
| 8 | no model yet | 91.2 [9.1 to 302.4] | no model yet |
| 12 | no model yet | 4.7 [3.2 to 6.7] | no model yet |
| 16 | 17.2 [3.4 to 306.6], 7 no model | 4.4 [2.5 to 6.2] | 308.2 [192.4 to 398.0] |
| 24 | 3.9 [2.8 to 10.5], 1 no model | 2.5 [1.9 to 3.0] | 238.5 [161.2 to 332.0] |
| 32 | 3.4 [2.2 to 3.9] | 2.7 [1.8 to 3.2] | 214.8 [115.8 to 240.7] |
| 48 | 2.5 [1.6 to 2.8] | 1.5 [1.4 to 2.5] | 134.9 [107.2 to 182.7] |
| 64 | 2.1 [1.6 to 2.9] | 1.5 [1.0 to 2.3] | 163.0 [91.0 to 206.1] |

## Damage mid run (break at motion 64; arm, gantry, scara, telescope, body type unknown)

| damage | swarm detected at (median motions after damage) | BodyScout swarm error at 128, mm | Single agent (chain model) error at 128, mm |
| --- | --- | --- | --- |
| bent_axis | 5.5 (18/20 runs) | 1.3 [1.2 to 1.9], 2 no model | 46.3 [39.9 to 69.3] |
| locked_joint | 2.0 (20/20 runs) | 1.5 [1.3 to 2.3], 1 no model | 45.4 [32.8 to 63.6] |
| long_link | 2.0 (20/20 runs) | 1.6 [1.3 to 2.2], 1 no model | 55.9 [40.3 to 77.5] |
| payload | not detected (0/20 runs) | 2.2 [1.5 to 3.5] | 37.2 [28.7 to 65.6] |
| reversed_motor | 2.5 (20/20 runs) | 1.6 [1.2 to 1.8], 1 no model | 77.0 [55.3 to 98.9] |
| tool | 2.0 (20/20 runs) | 1.5 [1.4 to 1.9], 1 no model | 88.0 [71.5 to 112.9] |

Gaps in the swarm curve are deliberate: between the alarm and the next crowned model the planner has no trusted model and refuses to move.

## Knowing when it is guessing

| targets | BodyScout refused | naive planner median miss, mm |
| --- | --- | --- |
| reachable | 0% | 1 |
| out of reach | 100% | 466 |
| arm, reachable | 0% | 2 |
| arm, out of reach | 100% | 407 |
| gantry, reachable | 0% | 1 |
| gantry, out of reach | 100% | 804 |
| scara, reachable | 0% | 1 |
| scara, out of reach | 100% | 459 |
| telescope, reachable | 0% | 1 |
| telescope, out of reach | 100% | 376 |

## Real arms from MuJoCo Menagerie, body type unknown (median over seeds)

| arm | channels | swarm reach, mm | single reach, mm | swarm joints right | single joints right |
| --- | --- | --- | --- | --- | --- |
| panda | ordered | 1.9 [1.8 to 2.0] | 340.3 [309.1 to 433.8] | 18/21 (observable 18/18) | 11/21 (observable 11/18) |
| panda | shuffled | 2.3 [2.0 to 3.1] | 505.9 [359.5 to 684.8] | 19/21 (observable 18/18) | 5/21 (observable 5/18) |
| ur5e | ordered | 2.2 [1.9 to 2.6] | 285.2 [221.9 to 473.7] | 16/18 (observable 15/15) | 8/18 (observable 7/15) |
| ur5e | shuffled | 1.6 [1.5 to 2.7] | 348.3 [252.4 to 455.6] | 16/18 (observable 15/15) | 5/18 (observable 5/15) |
| gen3 | ordered | 2.4 [1.8 to 2.5] | 392.3 [299.6 to 832.4] | 20/21 (observable 16/16) | 11/21 (observable 8/16) |
| gen3 | shuffled | 2.2 [1.8 to 2.3] | 591.6 [398.0 to 837.1] | 18/21 (observable 16/16) | 2/21 (observable 2/16) |
| vx300s | ordered | 2.3 [1.5 to 2.5] | 296.7 [113.2 to 332.3] | 15/18 (observable 15/15) | 7/18 (observable 7/15) |
| vx300s | shuffled | 2.1 [1.7 to 2.3] | 270.1 [227.4 to 443.5] | 15/18 (observable 15/15) | 5/18 (observable 5/15) |

## Unknown body types (median reach error at 64 motions [95% CI], mm; structure found)

| body | BodyScout swarm | Single agent (chain model) | swarm structure right | single structure right |
| --- | --- | --- | --- | --- |
| arm | 1.8 [1.2 to 2.7] | 220.8 [138.1 to 319.2] | 10/10 | 1/10 |
| gantry | 1.1 [0.9 to 1.1] | 59.2 [37.4 to 94.2] | 10/10 | 1/10 |
| scara | 1.3 [1.0 to 1.5] | 41.4 [17.8 to 101.0] | 10/10 | 2/10 |
| telescope | 1.3 [1.0 to 2.3] | 48.5 [20.0 to 205.3] | 10/10 | 2/10 |

## Failures we found

Every setting where the swarm misses (wrong structure in some run, damage not noticed, a false alarm, or a median over 10 mm) or a baseline's median beats the swarm's. Rows per family are included for faults and noise.

| experiment | setting | what happened | numbers |
| --- | --- | --- | --- |
| learning | 8 motions | Single agent (chain model) beats the swarm | 91.2 [9.1 to 302.4] vs swarm no model mm; intervals do not overlap |
| learning | 12 motions | Single agent (chain model) beats the swarm | 4.7 [3.2 to 6.7] vs swarm no model mm; intervals do not overlap |
| learning | 16 motions | Single agent (chain model) beats the swarm | 4.4 [2.5 to 6.2] vs swarm 17.2 [3.4 to 306.6], 7 no model mm; intervals overlap |
| learning | 16 motions | swarm median over 10 mm | 17.2 [3.4 to 306.6], 7 no model mm |
| learning | 24 motions | Single agent (chain model) beats the swarm | 2.5 [1.9 to 3.0] vs swarm 3.9 [2.8 to 10.5], 1 no model mm; intervals overlap |
| learning | 32 motions | Single agent (chain model) beats the swarm | 2.7 [1.8 to 3.2] vs swarm 3.4 [2.2 to 3.9] mm; intervals overlap |
| learning | 48 motions | Single agent (chain model) beats the swarm | 1.5 [1.4 to 2.5] vs swarm 2.5 [1.6 to 2.8] mm; intervals overlap |
| learning | 64 motions | Single agent (chain model) beats the swarm | 1.5 [1.0 to 2.3] vs swarm 2.1 [1.6 to 2.9] mm; intervals overlap |
| damage | bent_axis | swarm did not notice the damage | 2/20 runs |
| damage | payload | swarm did not notice the damage | 20/20 runs |
