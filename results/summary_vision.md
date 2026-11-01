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
