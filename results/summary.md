# BodyScout results summary

## Learning an unknown body (4 arms, median [IQR] reach error, mm)

| motions | BodyScout swarm | Single agent (chain model) | Single agent (neural net) |
| --- | --- | --- | --- |
| 8 | no model yet | 30.6 [13.0 to 99.0] | no model yet |
| 12 | no model yet | 5.9 [5.0 to 6.3] | no model yet |
| 16 | 211.8 [211.8 to 211.8] | 4.2 [3.5 to 5.0] | 362.7 [307.2 to 400.5] |
| 24 | 3.5 [3.2 to 3.9] | 2.8 [2.6 to 2.9] | 234.1 [190.7 to 292.4] |
| 32 | 3.5 [3.2 to 3.7] | 2.6 [2.2 to 2.9] | 130.2 [116.0 to 215.7] |
| 48 | 2.1 [1.5 to 2.6] | 2.1 [1.4 to 2.7] | 118.6 [104.0 to 163.7] |
| 64 | 2.2 [1.7 to 2.6] | 1.4 [1.0 to 2.1] | 163.0 [143.7 to 178.8] |

## Damage mid run (break at motion 48)

| damage | swarm detected at (median motions after damage) | swarm error at end, mm | single agent error at end, mm |
| --- | --- | --- | --- |
| bent_axis | 22.0 (1/3 runs) | 3.8 | 7.2 |
| long_link | 18.0 (3/3 runs) | 3.1 | 24.8 |
| reversed_motor | 18.0 (3/3 runs) | 2.7 | 43.5 |
| tool | 18.0 (3/3 runs) | 3.0 | 31.3 |

Gaps in the swarm curve are deliberate: between the alarm and the next crowned model the planner has no trusted model and refuses to move.

## Knowing when it is guessing

| targets | BodyScout refused | naive planner median miss, mm |
| --- | --- | --- |
| reachable | 0% | 2 |
| out of reach | 100% | 326 |

## Unknown body types (median reach error at 64 motions, mm; structure found)

| body | swarm | single agent | swarm structure right | single structure right |
| --- | --- | --- | --- | --- |
| arm | 2.2 | 213.8 | 3/3 | 1/3 |
| gantry | 0.9 | 46.8 | 3/3 | 1/3 |
| scara | 0.9 | 38.0 | 3/3 | 1/3 |
| telescope | 1.3 | 47.6 | 3/3 | 1/3 |
