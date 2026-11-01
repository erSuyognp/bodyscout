# BodyScout results summary

Cells are median reach error in mm [bootstrap 95% CI of the median, 2000 resamples] over runs.

**Read this first.** The swarm v2 fixes (two channel agents per channel probing from different poses, a review agent that rechecks doubtful channels from a third pose, a second chain modeler) were designed after we saw the fault preview on seeds 1 and 2 of the gantry and SCARA families, where one wrong channel finding or one crashed chain modeler sank the swarm. Seeds 101 and up were added after those fixes and are the independent check: tables split by seed show them separately. Swarm rows without swarm_version 2 in their meta come from the swarm before the fixes.

## Damage mid run (break at motion 64; gantry, scara, body type unknown)

| damage | swarm detected at (median motions after damage) | pipeline detected at (median motions after damage) | BodyScout swarm error at 128, mm | Fixed pipeline (same parts) error at 128, mm | Single agent (probes channels) error at 128, mm | Single agent (chain model) error at 128, mm |
| --- | --- | --- | --- | --- | --- | --- |
| long_link | 34.0 (4/4 runs) | 29.0 (4/4 runs) | 1.3 [1.3 to 1.3], 3 no model | 1.8 [1.5 to 2.4] | 26.3 [9.3 to 45.4] | 77.0 [69.0 to 79.0] |

Gaps in the swarm curve are deliberate: between the alarm and the next crowned model the planner has no trusted model and refuses to move.

## Unknown body types, preview seeds 1 to 10 (median reach error at 64 motions [95% CI], mm; structure found)

| body | BodyScout swarm | Fixed pipeline (same parts) | Single agent (probes channels) | Single agent (chain model) | swarm structure right | pipeline structure right | single_probe structure right | single structure right |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gantry | 1.4 [1.2 to 1.5] | 1.3 [1.3 to 1.3] | 0.9 [0.9 to 0.9] | 24.0 [1.1 to 46.8] | 2/2 | 2/2 | 2/2 | 1/2 |
| scara | 1.6 [1.5 to 1.7] | 1.3 [1.2 to 1.5] | 1.3 [1.3 to 1.4] | 19.8 [1.5 to 38.0] | 2/2 | 2/2 | 2/2 | 1/2 |

## Unknown body types, held out seeds 101 and up, the independent check (median reach error at 64 motions [95% CI], mm; structure found)

| body | BodyScout swarm | Fixed pipeline (same parts) | Single agent (probes channels) | Single agent (chain model) | swarm structure right | pipeline structure right | single_probe structure right | single structure right |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gantry | 1.2 [0.9 to 1.5] | 1.1 [0.8 to 1.3] | 0.9 [0.9 to 1.0] | 74.5 [44.6 to 104.3] | 2/2 | 2/2 | 2/2 | 0/2 |
| scara | 1.8 [0.9 to 2.7] | 1.8 [1.7 to 1.8] | 1.8 [1.3 to 2.3] | 29.5 [1.5 to 57.5] | 2/2 | 2/2 | 2/2 | 1/2 |

## Injected faults, unknown body (4 robots, median reach error at 64 motions [95% CI], mm), preview seeds 1 to 10

| fault | BodyScout swarm | Fixed pipeline (same parts) | Single agent (probes channels) | Single agent (chain model) | swarm structure right | pipeline structure right | single_probe structure right | single structure right |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 1.5 [1.2 to 1.7] | 1.3 [1.2 to 1.5] | 1.1 [0.9 to 1.4] | 19.8 [1.1 to 46.8] | 4/4 | 4/4 | 4/4 | 2/4 |
| wrong_finding | 1.4 [1.2 to 1.5] | 47.1 [27.7 to 94.3] | 35.8 [23.4 to 85.4] | 19.8 [1.1 to 46.8] (fault never fired) | 4/4 | 0/4 | 0/4 | 2/4 |
| bad_llm | 1.4 [1.1 to 1.5] | 26.4 [21.2 to 30.4] | 1.1 [0.9 to 1.4] (fault never fired) | 19.8 [1.1 to 46.8] (fault never fired) | 4/4 | 0/4 | 4/4 | 2/4 |
| modeler_crash | 1.1 [0.9 to 1.8] | no model | 2.4 [1.8 to 2.9] | 39.6 [2.4 to 82.9] | 4/4 | 0/4 | 4/4 | 1/4 |
| noisy_channel | 28.2 [3.8 to 41.8] | 29.3 [4.0 to 56.7] | 27.3 [3.0 to 49.6] | 19.8 [1.1 to 46.8] (fault never fired) | 1/4 | 1/4 | 1/4 | 2/4 |

## Injected faults, unknown body (4 robots, median reach error at 64 motions [95% CI], mm), held out seeds 101 and up, the independent check

| fault | BodyScout swarm | Fixed pipeline (same parts) | Single agent (probes channels) | Single agent (chain model) | swarm structure right | pipeline structure right | single_probe structure right | single structure right |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 1.2 [0.9 to 2.7] | 1.5 [0.8 to 1.8] | 1.1 [0.9 to 2.3] | 51.1 [1.5 to 104.3] | 4/4 | 4/4 | 4/4 | 1/4 |
| wrong_finding | 1.6 [1.0 to 1.9] | 29.5 [27.8 to 182.7] | 51.4 [32.3 to 84.3] | 51.1 [1.5 to 104.3] (fault never fired) | 4/4 | 0/4 | 0/4 | 1/4 |
| bad_llm | 1.8 [0.7 to 2.2] | 17.9 [17.6 to 73.6], 1 no model | 1.1 [0.9 to 2.3] (fault never fired) | 51.1 [1.5 to 104.3] (fault never fired) | 4/4 | 0/4 | 4/4 | 1/4 |
| modeler_crash | 1.1 [0.8 to 3.0] | no model | 3.8 [3.3 to 6.4] | 68.4 [51.6 to 116.3] | 4/4 | 0/4 | 4/4 | 0/4 |
| noisy_channel | 19.0 [4.3 to 44.1] | 30.3 [4.8 to 65.3] | 39.6 [4.4 to 61.4] | 51.1 [1.5 to 104.3] (fault never fired) | 1/4 | 1/4 | 1/4 | 1/4 |

wrong_finding flips one channel's reported joint type; bad_llm posts 3 confident wrong structures every epoch in an LLM's slot (the pipeline's LLM stage has the final say, so it adopts them); modeler_crash stops one chain modeler at motion 24; noisy_channel adds 20 mm noise to every sweep of one channel. Faults hit one agent instance; the swarm's replicas and second chain modeler are not faulted. 'Fault never fired' means the condition has no slot for it (a single agent has no findings and no hypothesis source), so it ran unchanged.

## Camera noise sweep, unknown body (4 robots, median reach error at 64 motions [95% CI], mm)

| noise mm | BodyScout swarm | Fixed pipeline (same parts) | Single agent (probes channels) | Single agent (chain model) | swarm structure right | pipeline structure right | single_probe structure right | single structure right |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.7 [0.6 to 1.2] | 1.0 [0.7 to 1.3] | 0.7 [0.5 to 1.1] | 20.2 [0.6 to 40.4] | 4/4 | 4/4 | 4/4 | 2/4 |
| 2 | 1.5 [1.2 to 1.7] | 1.3 [1.2 to 1.5] | 1.1 [0.9 to 1.4] | 19.8 [1.1 to 46.8] | 4/4 | 4/4 | 4/4 | 2/4 |
| 5 | 2.9 [2.8 to 5.4] | 2.7 [2.5 to 4.1] | 2.2 [2.0 to 2.7] | 22.8 [2.3 to 58.4] | 4/4 | 4/4 | 4/4 | 2/4 |
| 10 | 17.4 [5.9 to 28.3] | 30.2 [29.1 to 103.8] | 36.2 [23.7 to 88.6] | 24.1 [3.8 to 48.3] | 2/4 | 0/4 | 0/4 | 2/4 |

False alarms (monitor declared damage on an undamaged body), runs with any / runs:

| noise mm | swarm | pipeline |
| --- | --- | --- |
| 1 | 0/4 | 0/4 |
| 2 | 0/4 | 0/4 |
| 5 | 0/4 | 0/4 |
| 10 | 0/4 | 0/4 |

## Cost per run (median [95% CI]): motions spent, of them single channel sweeps, and agent CPU seconds (scoring excluded)

| experiment | condition | runs | motions used | probe motions | agent CPU s |
| --- | --- | --- | --- | --- | --- |
| bodies | swarm | 8 | 64.0 [64.0 to 65.0] | 32.0 [32.0 to 32.0] | 86.1 [62.9 to 124.5] |
| bodies | pipeline | 8 | 68.0 [68.0 to 68.0] | 16.0 [16.0 to 16.0] | 3.0 [2.2 to 3.7] |
| bodies | single_probe | 8 | 64.0 [64.0 to 64.0] | 16.0 [16.0 to 16.0] | 5.2 [4.1 to 6.9] |
| bodies | single | 8 | 64.0 [64.0 to 64.0] | 0.0 [0.0 to 0.0] | 6.5 [5.9 to 7.6] |
| damage | swarm | 4 | 133.0 [128.0 to 135.0] | 80.0 [64.0 to 80.0] | 142.4 [88.1 to 467.5] |
| damage | pipeline | 4 | 132.0 [132.0 to 132.0] | 32.0 [32.0 to 32.0] | 5.5 [4.2 to 7.5] |
| damage | single_probe | 4 | 128.0 [128.0 to 128.0] | 16.0 [16.0 to 16.0] | 11.9 [11.0 to 12.8] |
| damage | single | 4 | 128.0 [128.0 to 128.0] | 0.0 [0.0 to 0.0] | 16.4 [14.2 to 19.2] |
| faults | swarm | 40 | 64.5 [64.0 to 65.0] | 32.0 [32.0 to 32.0] | 62.0 [50.7 to 85.2] |
| faults | pipeline | 40 | 68.0 [68.0 to 68.0] | 16.0 [16.0 to 16.0] | 4.9 [3.2 to 7.2] |
| faults | single_probe | 40 | 64.0 [64.0 to 64.0] | 16.0 [16.0 to 16.0] | 5.6 [4.1 to 7.1] |
| faults | single | 40 | 64.0 [64.0 to 64.0] | 0.0 [0.0 to 0.0] | 5.6 [5.1 to 6.6] |
| noise | swarm | 16 | 65.0 [64.0 to 65.0] | 32.0 [32.0 to 40.0] | 64.7 [40.3 to 94.8] |
| noise | pipeline | 16 | 68.0 [68.0 to 68.0] | 16.0 [16.0 to 16.0] | 4.4 [2.2 to 7.1] |
| noise | single_probe | 16 | 64.0 [64.0 to 64.0] | 16.0 [16.0 to 16.0] | 7.4 [4.6 to 19.8] |
| noise | single | 16 | 64.0 [64.0 to 64.0] | 0.0 [0.0 to 0.0] | 7.4 [7.0 to 8.1] |

## Failures we found

Numbers are reach error in mm, median [95% CI]. Every setting where the swarm misses (wrong structure in some run, damage not noticed, a false alarm, or a median over 10 mm) or a baseline's median beats the swarm's. Rows per family are included for faults and noise.

| experiment | setting | what happened | numbers |
| --- | --- | --- | --- |
| bodies, preview seeds 1 to 10 | gantry | Fixed pipeline (same parts) beats the swarm | 1.3 [1.3 to 1.3] vs swarm 1.4 [1.2 to 1.5]; intervals overlap |
| bodies, preview seeds 1 to 10 | gantry | Single agent (probes channels) beats the swarm | 0.9 [0.9 to 0.9] vs swarm 1.4 [1.2 to 1.5]; intervals do not overlap |
| bodies, preview seeds 1 to 10 | scara | Fixed pipeline (same parts) beats the swarm | 1.3 [1.2 to 1.5] vs swarm 1.6 [1.5 to 1.7]; intervals overlap |
| bodies, preview seeds 1 to 10 | scara | Single agent (probes channels) beats the swarm | 1.3 [1.3 to 1.4] vs swarm 1.6 [1.5 to 1.7]; intervals do not overlap |
| bodies, held out seeds 101 and up | gantry | Fixed pipeline (same parts) beats the swarm | 1.1 [0.8 to 1.3] vs swarm 1.2 [0.9 to 1.5]; intervals overlap |
| bodies, held out seeds 101 and up | gantry | Single agent (probes channels) beats the swarm | 0.9 [0.9 to 1.0] vs swarm 1.2 [0.9 to 1.5]; intervals overlap |
| faults, preview seeds 1 to 10 | none | Fixed pipeline (same parts) beats the swarm | 1.3 [1.2 to 1.5] vs swarm 1.5 [1.2 to 1.7]; intervals overlap |
| faults, preview seeds 1 to 10 | none | Single agent (probes channels) beats the swarm | 1.1 [0.9 to 1.4] vs swarm 1.5 [1.2 to 1.7]; intervals overlap |
| faults, preview seeds 1 to 10 | none, gantry | Fixed pipeline (same parts) beats the swarm | 1.3 [1.3 to 1.3] vs swarm 1.4 [1.2 to 1.5]; intervals overlap |
| faults, preview seeds 1 to 10 | none, gantry | Single agent (probes channels) beats the swarm | 0.9 [0.9 to 0.9] vs swarm 1.4 [1.2 to 1.5]; intervals do not overlap |
| faults, preview seeds 1 to 10 | none, scara | Fixed pipeline (same parts) beats the swarm | 1.3 [1.2 to 1.5] vs swarm 1.6 [1.5 to 1.7]; intervals overlap |
| faults, preview seeds 1 to 10 | none, scara | Single agent (probes channels) beats the swarm | 1.3 [1.3 to 1.4] vs swarm 1.6 [1.5 to 1.7]; intervals do not overlap |
| faults, preview seeds 1 to 10 | bad_llm | Single agent (probes channels) beats the swarm | 1.1 [0.9 to 1.4] vs swarm 1.4 [1.1 to 1.5]; intervals overlap |
| faults, preview seeds 1 to 10 | bad_llm, gantry | Single agent (probes channels) beats the swarm | 0.9 [0.9 to 0.9] vs swarm 1.4 [1.3 to 1.5]; intervals do not overlap |
| faults, preview seeds 1 to 10 | noisy_channel | Single agent (probes channels) beats the swarm | 27.3 [3.0 to 49.6] vs swarm 28.2 [3.8 to 41.8]; intervals overlap |
| faults, preview seeds 1 to 10 | noisy_channel | Single agent (chain model) beats the swarm | 19.8 [1.1 to 46.8] vs swarm 28.2 [3.8 to 41.8]; intervals overlap |
| faults, preview seeds 1 to 10 | noisy_channel | swarm structure wrong | 3/4 runs |
| faults, preview seeds 1 to 10 | noisy_channel | swarm median over 10 mm | 28.2 [3.8 to 41.8] |
| faults, preview seeds 1 to 10 | noisy_channel, gantry | Single agent (chain model) beats the swarm | 24.0 [1.1 to 46.8] vs swarm 28.2 [24.8 to 31.6]; intervals overlap |
| faults, preview seeds 1 to 10 | noisy_channel, gantry | swarm structure wrong | 2/2 runs |
| faults, preview seeds 1 to 10 | noisy_channel, gantry | swarm median over 10 mm | 28.2 [24.8 to 31.6] |
| faults, preview seeds 1 to 10 | noisy_channel, scara | Fixed pipeline (same parts) beats the swarm | 19.2 [4.0 to 34.4] vs swarm 22.8 [3.8 to 41.8]; intervals overlap |
| faults, preview seeds 1 to 10 | noisy_channel, scara | Single agent (probes channels) beats the swarm | 17.3 [3.0 to 31.6] vs swarm 22.8 [3.8 to 41.8]; intervals overlap |
| faults, preview seeds 1 to 10 | noisy_channel, scara | Single agent (chain model) beats the swarm | 19.8 [1.5 to 38.0] vs swarm 22.8 [3.8 to 41.8]; intervals overlap |
| faults, preview seeds 1 to 10 | noisy_channel, scara | swarm structure wrong | 1/2 runs |
| faults, preview seeds 1 to 10 | noisy_channel, scara | swarm median over 10 mm | 22.8 [3.8 to 41.8] |
| faults, held out seeds 101 and up | none | Single agent (probes channels) beats the swarm | 1.1 [0.9 to 2.3] vs swarm 1.2 [0.9 to 2.7]; intervals overlap |
| faults, held out seeds 101 and up | none, gantry | Fixed pipeline (same parts) beats the swarm | 1.1 [0.8 to 1.3] vs swarm 1.2 [0.9 to 1.5]; intervals overlap |
| faults, held out seeds 101 and up | none, gantry | Single agent (probes channels) beats the swarm | 0.9 [0.9 to 1.0] vs swarm 1.2 [0.9 to 1.5]; intervals overlap |
| faults, held out seeds 101 and up | bad_llm | Single agent (probes channels) beats the swarm | 1.1 [0.9 to 2.3] vs swarm 1.8 [0.7 to 2.2]; intervals overlap |
| faults, held out seeds 101 and up | bad_llm, gantry | Single agent (probes channels) beats the swarm | 0.9 [0.9 to 1.0] vs swarm 1.1 [0.7 to 1.6]; intervals overlap |
| faults, held out seeds 101 and up | bad_llm, scara | Single agent (probes channels) beats the swarm | 1.8 [1.3 to 2.3] vs swarm 2.1 [2.0 to 2.2]; intervals overlap |
| faults, held out seeds 101 and up | noisy_channel | swarm structure wrong | 3/4 runs |
| faults, held out seeds 101 and up | noisy_channel | swarm median over 10 mm | 19.0 [4.3 to 44.1] |
| faults, held out seeds 101 and up | noisy_channel, gantry | swarm structure wrong | 2/2 runs |
| faults, held out seeds 101 and up | noisy_channel, gantry | swarm median over 10 mm | 19.0 [11.4 to 26.6] |
| faults, held out seeds 101 and up | noisy_channel, scara | Fixed pipeline (same parts) beats the swarm | 18.2 [4.8 to 31.5] vs swarm 24.2 [4.3 to 44.1]; intervals overlap |
| faults, held out seeds 101 and up | noisy_channel, scara | swarm structure wrong | 1/2 runs |
| faults, held out seeds 101 and up | noisy_channel, scara | swarm median over 10 mm | 24.2 [4.3 to 44.1] |
| noise | 1, gantry | Single agent (probes channels) beats the swarm | 0.5 [0.5 to 0.6] vs swarm 0.6 [0.6 to 0.6]; intervals do not overlap |
| noise | 2 | Fixed pipeline (same parts) beats the swarm | 1.3 [1.2 to 1.5] vs swarm 1.5 [1.2 to 1.7]; intervals overlap |
| noise | 2 | Single agent (probes channels) beats the swarm | 1.1 [0.9 to 1.4] vs swarm 1.5 [1.2 to 1.7]; intervals overlap |
| noise | 2, gantry | Fixed pipeline (same parts) beats the swarm | 1.3 [1.3 to 1.3] vs swarm 1.4 [1.2 to 1.5]; intervals overlap |
| noise | 2, gantry | Single agent (probes channels) beats the swarm | 0.9 [0.9 to 0.9] vs swarm 1.4 [1.2 to 1.5]; intervals do not overlap |
| noise | 2, scara | Fixed pipeline (same parts) beats the swarm | 1.3 [1.2 to 1.5] vs swarm 1.6 [1.5 to 1.7]; intervals overlap |
| noise | 2, scara | Single agent (probes channels) beats the swarm | 1.3 [1.3 to 1.4] vs swarm 1.6 [1.5 to 1.7]; intervals do not overlap |
| noise | 5 | Fixed pipeline (same parts) beats the swarm | 2.7 [2.5 to 4.1] vs swarm 2.9 [2.8 to 5.4]; intervals overlap |
| noise | 5 | Single agent (probes channels) beats the swarm | 2.2 [2.0 to 2.7] vs swarm 2.9 [2.8 to 5.4]; intervals do not overlap |
| noise | 5, gantry | Single agent (probes channels) beats the swarm | 2.1 [2.0 to 2.2] vs swarm 2.9 [2.9 to 3.0]; intervals do not overlap |
| noise | 5, scara | Fixed pipeline (same parts) beats the swarm | 2.7 [2.5 to 2.8] vs swarm 4.1 [2.8 to 5.4]; intervals overlap |
| noise | 5, scara | Single agent (probes channels) beats the swarm | 2.5 [2.3 to 2.7] vs swarm 4.1 [2.8 to 5.4]; intervals do not overlap |
| noise | 10 | swarm structure wrong | 2/4 runs |
| noise | 10 | swarm median over 10 mm | 17.4 [5.9 to 28.3] |
| noise | 10, gantry | swarm structure wrong | 1/2 runs |
| noise | 10, gantry | swarm median over 10 mm | 17.0 [5.9 to 28.2] |
| noise | 10, scara | swarm structure wrong | 1/2 runs |
| noise | 10, scara | swarm median over 10 mm | 17.5 [6.7 to 28.3] |
