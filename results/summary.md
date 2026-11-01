# BodyScout results summary

Cells are median reach error in mm [bootstrap 95% CI of the median, 2000 resamples] over runs.

## Learning an unknown body (4 arms, median reach error [95% CI], mm)

| motions | BodyScout swarm | Single agent (chain model) | Single agent (neural net) |
| --- | --- | --- | --- |
| 8 | no model yet | 30.6 [4.9 to 259.7] | no model yet |
| 12 | no model yet | 5.9 [3.2 to 6.9] | no model yet |
| 16 | 306.6 [306.6 to 306.6], 3 no model | 4.2 [2.4 to 6.2] | 362.7 [201.5 to 452.6] |
| 24 | 4.6 [2.4 to 306.6] | 2.8 [2.0 to 3.0] | 234.1 [120.5 to 407.5] |
| 32 | 3.5 [2.5 to 5.6] | 2.6 [1.3 to 3.3] | 130.2 [115.3 to 430.5] |
| 48 | 2.2 [1.3 to 3.7] | 2.1 [1.3 to 2.7] | 118.6 [94.1 to 265.1] |
| 64 | 2.0 [1.4 to 3.6] | 1.4 [1.0 to 2.9] | 163.0 [90.7 to 221.3] |

## Damage mid run (break at motion 48)

| damage | swarm detected at (median motions after damage) | BodyScout swarm error at 112, mm | Single agent (chain model) error at 112, mm |
| --- | --- | --- | --- |
| bent_axis | 33.5 (2/3 runs) | 2.5 [1.3 to 24.1] | 7.2 [1.6 to 8.1] |
| long_link | 20.0 (3/3 runs) | 2.8 [2.7 to 4.2] | 24.8 [17.6 to 34.3] |
| reversed_motor | 20.0 (3/3 runs) | 2.9 [2.7 to 4.4] | 43.5 [42.3 to 66.6] |
| tool | 20.0 (3/3 runs) | 2.7 [2.6 to 5.4] | 31.3 [11.6 to 34.3] |

Gaps in the swarm curve are deliberate: between the alarm and the next crowned model the planner has no trusted model and refuses to move.

## Knowing when it is guessing

| targets | BodyScout refused | naive planner median miss, mm |
| --- | --- | --- |
| reachable | 0% | 2 |
| out of reach | 100% | 326 |

## Real arms from MuJoCo Menagerie, body type unknown (median over seeds)

| arm | channels | swarm reach, mm | single reach, mm | swarm joints right | single joints right |
| --- | --- | --- | --- | --- | --- |
| panda | ordered | 1.5 [1.2 to 1.9] | 364.7 [291.4 to 438.0] | 13/14 (observable 12/12) | 7/14 (observable 7/12) |
| panda | shuffled | 2.1 [1.8 to 2.4] | 610.3 [538.3 to 682.3] | 14/14 (observable 12/12) | 3/14 (observable 3/12) |
| ur5e | ordered | 1.5 [1.4 to 1.6] | 271.6 [263.9 to 279.4] | 10/12 (observable 10/10) | 6/12 (observable 5/10) |
| ur5e | shuffled | 1.9 [1.7 to 2.1] | 370.1 [322.8 to 417.3] | 12/12 (observable 10/10) | 2/12 (observable 2/10) |

## Unknown body types (median reach error at 64 motions [95% CI], mm; structure found)

| body | BodyScout swarm | Single agent (chain model) | swarm structure right | single structure right |
| --- | --- | --- | --- | --- |
| arm | 2.5 [1.3 to 2.6] | 213.8 [1.0 to 252.4] | 3/3 | 1/3 |
| gantry | 1.1 [0.9 to 1.5] | 46.8 [1.1 to 47.0] | 3/3 | 1/3 |
| scara | 1.7 [1.0 to 2.0] | 38.0 [1.5 to 180.2] | 3/3 | 1/3 |
| telescope | 1.7 [0.9 to 2.0] | 47.6 [1.3 to 205.2] | 3/3 | 1/3 |

## Failures we found

Every setting where the swarm misses (wrong structure in some run, damage not noticed, a false alarm, or a median over 10 mm) or a baseline's median beats the swarm's. Rows per family are included for faults and noise.

| experiment | setting | what happened | numbers |
| --- | --- | --- | --- |
| learning | 8 motions | Single agent (chain model) beats the swarm | 30.6 [4.9 to 259.7] vs swarm no model mm; intervals do not overlap |
| learning | 12 motions | Single agent (chain model) beats the swarm | 5.9 [3.2 to 6.9] vs swarm no model mm; intervals do not overlap |
| learning | 16 motions | Single agent (chain model) beats the swarm | 4.2 [2.4 to 6.2] vs swarm 306.6 [306.6 to 306.6], 3 no model mm; intervals do not overlap |
| learning | 16 motions | swarm median over 10 mm | 306.6 [306.6 to 306.6], 3 no model mm |
| learning | 24 motions | Single agent (chain model) beats the swarm | 2.8 [2.0 to 3.0] vs swarm 4.6 [2.4 to 306.6] mm; intervals overlap |
| learning | 32 motions | Single agent (chain model) beats the swarm | 2.6 [1.3 to 3.3] vs swarm 3.5 [2.5 to 5.6] mm; intervals overlap |
| learning | 48 motions | Single agent (chain model) beats the swarm | 2.1 [1.3 to 2.7] vs swarm 2.2 [1.3 to 3.7] mm; intervals overlap |
| learning | 64 motions | Single agent (chain model) beats the swarm | 1.4 [1.0 to 2.9] vs swarm 2.0 [1.4 to 3.6] mm; intervals overlap |
| damage | bent_axis | swarm did not notice the damage | 1/3 runs |
