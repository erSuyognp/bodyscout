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

## Making markerless precise (V5)

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

## Telling the camera what it is looking at: SCARA (V6)

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

## Swarm learns from cameras (V3)

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

### Where camera input makes things worse

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
