---
name: robot_motion
description: Command the channels of an unknown jointed robot (arm, gantry, SCARA, telescope) and observe its 3D tip position
metadata:
---

# Robot Motion (BodyScout)

The only window onto a black box robot. Send command vectors to its unlabeled channels,
let the servos settle, and read back a noisy (about 2 mm) fingertip position. Nothing else
about the body is returned: no joint types, no link lengths, no model file. Each motion
costs one unit of the experiment's motion budget.

Use it to collect training or holdout data for robot self modeling, kinematic structure
discovery, and damage detection. Output rows pair a command `q` with the observed tip `x_mm`.

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--query` | Free text; a body handle such as `arm3` or `scara7` selects the robot | `arm3` |
| `--family` | `arm`, `gantry`, `scara` or `telescope` (overrides the query) | from query |
| `--seed` | Which body of the family | from query |
| `--commands` | JSON list of command vectors, one value per channel, each in [-2, 2] | random |
| `--n` | Number of random motions when `--commands` is absent | 8 |
| `--motion-seed` | Seed for the random motions | 0 |
| `--damage` | Damage the body before moving (`long_link`, `tool`, ...) | none |
| `--format` | `json` or `summary` | json |

## Examples

```bash
python3 {baseDir}/scripts/robot_motion.py --query "probe arm3" --n 5 --format json
python3 {baseDir}/scripts/robot_motion.py --family scara --seed 7 --commands "[[0,0,0,0],[0.5,0,0,0]]" --format json
```

## Output

```json
{"query": "probe arm3", "body": "arm3", "damaged": false, "n_channels": 4, "limits": [-2.0, 2.0],
 "motions": 5, "results": [{"q": [0.1, -0.4, 1.2, 0.0], "x_mm": [112.4, -3.1, 208.9]}],
 "summary": "5 motions on a 4 channel body, tip in mm"}
```
