# BodyScout results summary

## Learning an unknown body (10 arms, median [IQR] reach error, mm)

| motions | BodyScout swarm | Single agent (chain model) | Single agent (neural net) |
| --- | --- | --- | --- |
| 8 | no model yet | 91.2 [10.7 to 267.8] | no model yet |
| 12 | no model yet | 4.7 [3.3 to 6.2] | no model yet |
| 16 | 17.2 [10.3 to 161.9] | 4.4 [2.7 to 6.1] | 308.2 [238.8 to 381.9] |
| 24 | 3.9 [3.3 to 5.3] | 2.5 [2.2 to 3.0] | 238.5 [176.8 to 325.8] |
| 32 | 3.4 [2.4 to 3.8] | 2.7 [1.8 to 3.1] | 214.8 [123.3 to 239.4] |
| 48 | 2.5 [1.7 to 2.8] | 1.5 [1.5 to 2.2] | 134.9 [108.9 to 147.0] |
| 64 | 2.1 [1.6 to 2.8] | 1.5 [1.0 to 2.1] | 163.0 [101.4 to 198.2] |

## Damage mid run (break at motion 64; arm, gantry, scara, telescope, body type unknown)

| damage | swarm detected at (median motions after damage) | swarm error at end, mm | single agent error at end, mm |
| --- | --- | --- | --- |
| bent_axis | 5.5 (18/20 runs) | 1.3 | 46.3 |
| locked_joint | 2.0 (20/20 runs) | 1.5 | 45.4 |
| long_link | 2.0 (20/20 runs) | 1.6 | 55.9 |
| payload | not detected (0/20 runs) | 2.2 | 37.2 |
| reversed_motor | 2.5 (20/20 runs) | 1.6 | 77.0 |
| tool | 2.0 (20/20 runs) | 1.5 | 88.0 |

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
| panda | ordered | 1.9 | 340.3 | 18/21 (observable 18/18) | 11/21 (observable 11/18) |
| panda | shuffled | 2.3 | 505.9 | 19/21 (observable 18/18) | 5/21 (observable 5/18) |
| ur5e | ordered | 2.2 | 285.2 | 16/18 (observable 15/15) | 8/18 (observable 7/15) |
| ur5e | shuffled | 1.6 | 348.3 | 16/18 (observable 15/15) | 5/18 (observable 5/15) |
| gen3 | ordered | 2.4 | 392.3 | 20/21 (observable 16/16) | 11/21 (observable 8/16) |
| gen3 | shuffled | 2.2 | 591.6 | 18/21 (observable 16/16) | 2/21 (observable 2/16) |
| vx300s | ordered | 2.3 | 296.7 | 15/18 (observable 15/15) | 7/18 (observable 7/15) |
| vx300s | shuffled | 2.1 | 270.1 | 15/18 (observable 15/15) | 5/18 (observable 5/15) |

## Unknown body types (median reach error at 64 motions, mm; structure found)

| body | swarm | single agent | swarm structure right | single structure right |
| --- | --- | --- | --- | --- |
| arm | 1.8 | 220.8 | 10/10 | 1/10 |
| gantry | 1.1 | 59.2 | 10/10 | 1/10 |
| scara | 1.3 | 41.4 | 10/10 | 2/10 |
| telescope | 1.3 | 48.5 | 10/10 | 2/10 |
