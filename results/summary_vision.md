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
