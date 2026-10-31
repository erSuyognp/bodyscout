# BodyScout results summary

## Learning an unknown body (4 arms, median [IQR] reach error, mm)

| motions | BodyScout swarm | Single agent (chain model) | Single agent (neural net) |
| --- | --- | --- | --- |
| 8 | no model yet | 13.4 [9.4 to 15.8] | no model yet |
| 12 | no model yet | 5.0 [4.5 to 5.6] | no model yet |
| 16 | 9.6 [9.0 to 10.1] | 4.0 [3.6 to 4.6] | 362.7 [302.1 to 400.5] |
| 24 | 3.3 [2.9 to 4.1] | 2.6 [2.0 to 56.0] | 288.8 [228.8 to 336.4] |
| 32 | 3.0 [2.3 to 3.9] | 2.2 [1.8 to 2.8] | 143.4 [124.3 to 227.2] |
| 48 | 1.9 [1.6 to 2.3] | 1.6 [1.3 to 2.2] | 112.9 [93.9 to 165.1] |
| 64 | 1.7 [1.5 to 1.7] | 1.6 [1.0 to 2.3] | 122.5 [94.8 to 160.5] |

## Damage mid run (break at motion 48)

| damage | swarm detected at (median motions after damage) | swarm error at end, mm | single agent error at end, mm |
| --- | --- | --- | --- |
| bent_axis | not detected (0/3 runs) | 13.1 | 8.1 |
| long_link | 19.0 (3/3 runs) | 3.4 | 24.8 |
| reversed_motor | 19.0 (3/3 runs) | 3.2 | 43.5 |
| tool | 19.0 (3/3 runs) | 2.2 | 33.2 |

Gaps in the swarm curve are deliberate: between the alarm and the next crowned model the planner has no trusted model and refuses to move.

## Knowing when it is guessing

| targets | BodyScout refused | naive planner median miss, mm |
| --- | --- | --- |
| reachable | 0% | 2 |
| out of reach | 100% | 326 |

## Unknown body types (median reach error at 64 motions, mm; structure found)

| body | swarm | single agent | swarm structure right | single structure right |
| --- | --- | --- | --- | --- |
| arm | 2.1 | 213.8 | 3/3 | 1/3 |
| gantry | 1.1 | 42.2 | 3/3 | 1/3 |
| scara | 1.3 | 35.4 | 3/3 | 1/3 |
| telescope | 0.9 | 47.6 | 3/3 | 1/3 |
