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

## Real arms from MuJoCo Menagerie, body type unknown (median over seeds)

| arm | channels | swarm reach, mm | single reach, mm | swarm joints right | single joints right |
| --- | --- | --- | --- | --- | --- |
| panda | ordered | 1.5 | 364.7 | 13/14 (observable 12/12) | 7/14 (observable 7/12) |
| panda | shuffled | 2.1 | 610.3 | 14/14 (observable 12/12) | 3/14 (observable 3/12) |
| ur5e | ordered | 1.5 | 271.6 | 10/12 (observable 10/10) | 6/12 (observable 5/10) |
| ur5e | shuffled | 1.9 | 370.1 | 12/12 (observable 10/10) | 2/12 (observable 2/10) |

## Unknown body types (median reach error at 64 motions, mm; structure found)

| body | swarm | single agent | swarm structure right | single structure right |
| --- | --- | --- | --- | --- |
| arm | 2.5 | 213.8 | 3/3 | 1/3 |
| gantry | 1.1 | 46.8 | 3/3 | 1/3 |
| scara | 1.7 | 38.0 | 3/3 | 1/3 |
| telescope | 1.7 | 47.6 | 3/3 | 1/3 |

# Vision: two cameras instead of a marker

## Detector 1: red tip sphere, two fixed cameras (V1)

Two fixed cameras (front at (2.0, 0.0, 0.85) m, fovy 50.0 deg, side at (0.0, -2.0, 0.85) m, fovy 50.0 deg), 640x480, rendered with EGL on NVIDIA H200/PCIe/SSE2. Camera matrices come from the MuJoCo camera parameters only. Per family: 5 bodies x 40 random poses. Error is the distance between the triangulated and the true rendered tip.

| family | poses | detected in both views | hidden (in view, covered) | out of view | median error, mm | 90th percentile, mm | median pixel error | median ray gap, mm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arm | 200 | 189 (94%) | 11 (6%) | 0 (0%) | 3.7 | 6.9 | 0.67 | 1.3 |
| gantry | 200 | 200 (100%) | 0 (0%) | 0 (0%) | 3.0 | 6.5 | 0.32 | 0.6 |
| scara | 200 | 194 (97%) | 6 (3%) | 0 (0%) | 4.3 | 6.9 | 0.35 | 0.8 |
| telescope | 200 | 193 (96%) | 7 (4%) | 0 (0%) | 3.1 | 6.6 | 0.55 | 1.1 |

Hidden and out of view poses return NaN instead of a guess. For comparison, the marker robot's simulated camera noise is 2 mm per axis (about 3.5 mm as a 3D distance).

Detector note: the colour rule was changed once before this run, after a check on 110 views of other poses showed brightness weighting biased the centroid about 0.9 px upward (overhead light shades the lower half of the sphere).

## Detector 2: no marker, Gemini Robotics ER (V2)

Same 200 poses per family as above. Markerless: the tip sphere is painted like the links. Gemini (`models/gemini-robotics-er-2-preview`, temperature 0) is asked to point to the end of the robot's last link in each view; its normalized [y, x] point is triangulated as before. 1600 images, 1600 real calls this run (answers are cached by image hash, so reruns are free), 0 call errors. "Bad disagreement" = the two views' rays miss each other by more than 20 mm.

| family | poses | colour marker: located | colour: median / p90, mm | Gemini markerless: located | Gemini: median / p90, mm | Gemini views disagree badly (> 20 mm) | Gemini median pixel error |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm | 200 | 189 (94%) | 3.7 / 6.9 | 200 (100%) | 6.3 / 25.7 | 22 of 200 (11%) | 1.4 |
| gantry | 200 | 200 (100%) | 3.0 / 6.5 | 200 (100%) | 6.7 / 15.3 | 18 of 200 (9%) | 1.3 |
| scara | 200 | 194 (97%) | 4.3 / 6.9 | 200 (100%) | 189.9 / 293.7 | 60 of 200 (30%) | 22.0 |
| telescope | 200 | 193 (96%) | 3.1 / 6.6 | 200 (100%) | 6.3 / 14.4 | 13 of 200 (6%) | 1.4 |

Located = a point in both views (Gemini: it answered with a point in both; colour: the red sphere was visible in both). Markerless mode has no fallback; the colour detector is only a fallback in marker mode.

## Swarm learns from cameras (V3)

Unknown body mode, 2 seeds per family, budget 64 motions, same swarm and scorer in every condition; reach error and structure are scored on the true tip. Camera readings whose views disagree (rays > 20 mm apart) or that miss the tip are rejected as bad observations, never as body changes.

| family | condition | structure found | median reach error, mm | bad observations (of motions) | Monitor alarms |
| --- | --- | --- | --- | --- | --- |
| arm | marker (no camera) | 2/2 | 1.7 | 0 of 140 | 0 |
| arm | two cameras, red marker | 2/2 | 3.6 | 25 of 134 | 0 |
| arm | two cameras, no marker (Gemini) | 2/2 | 45.5 | 34 of 140 | 0 |
| gantry | marker (no camera) | 2/2 | 1.1 | 0 of 128 | 0 |
| gantry | two cameras, red marker | 2/2 | 3.0 | 0 of 128 | 0 |
| gantry | two cameras, no marker (Gemini) | 2/2 | 7.4 | 8 of 136 | 0 |
| scara | marker (no camera) | 2/2 | 1.3 | 0 of 128 | 0 |
| scara | two cameras, red marker | 2/2 | 3.5 | 7 of 128 | 0 |
| scara | two cameras, no marker (Gemini) | 1/2 | 77.0 | 38 of 136 | 0 |
| telescope | marker (no camera) | 2/2 | 1.0 | 0 of 130 | 0 |
| telescope | two cameras, red marker | 2/2 | 3.3 | 15 of 128 | 0 |
| telescope | two cameras, no marker (Gemini) | 2/2 | 10.0 | 38 of 136 | 0 |

### Where camera input makes things worse

- arm, two cameras, red marker: median reach error 3.6 mm vs 1.7 mm with the marker
- arm, two cameras, no marker (Gemini): median reach error 45.5 mm vs 1.7 mm with the marker
- gantry, two cameras, red marker: median reach error 3.0 mm vs 1.1 mm with the marker
- gantry, two cameras, no marker (Gemini): median reach error 7.4 mm vs 1.1 mm with the marker
- scara, two cameras, red marker: median reach error 3.5 mm vs 1.3 mm with the marker
- scara, two cameras, no marker (Gemini): structure found 1/2 vs 2/2 with the marker
- scara, two cameras, no marker (Gemini): median reach error 77.0 mm vs 1.3 mm with the marker
- telescope, two cameras, red marker: median reach error 3.3 mm vs 1.0 mm with the marker
- telescope, two cameras, no marker (Gemini): median reach error 10.0 mm vs 1.0 mm with the marker

Notes: a camera reading that is rejected still costs its motion. A rejected reading resets the stock Monitor's strike count (its NaN surprise is never above threshold), which can delay a real alarm by one sentinel. LLM hypothesizers are off in every condition so the only model in the loop is the detector.
