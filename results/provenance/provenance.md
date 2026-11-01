# Provenance of crowned champions (800 boards, 3875 champions)

Agent types: distinct agent types among a champion's ancestors, median (range). Competing: champions whose model was fit with hypotheses from two or more sources, and how many of those had sources whose first structures disagreed. Won: whose proposal the champion's structure came from (fit = no hypothesis had it). Pipeline authors are stages of one orchestrator, not independent agents.

## Every champion

| experiment | setting | condition | champions | agent types | competing (disagreed) | won | structure right |
| --- | --- | --- | --- | --- | --- | --- | --- |
| damage | bent_axis | pipeline | 218 | 7 (6 to 7) | 0 (0) | channels 218 | 218/218 |
| damage | bent_axis | swarm | 80 | 7 (6 to 9) | 78 (78) | channels 79, fit 1 | 80/80 |
| damage | locked_joint | pipeline | 224 | 7 (6 to 7) | 0 (0) | channels 215, fit 9 | 188/224 |
| damage | locked_joint | swarm | 79 | 7 (4 to 9) | 57 (57) | channels 66, fit 12, prior 1 | 70/79 |
| damage | long_link | pipeline | 228 | 6 (6 to 7) | 0 (0) | channels 228 | 228/228 |
| damage | long_link | swarm | 85 | 7 (4 to 9) | 79 (79) | channels 79, fit 6 | 85/85 |
| damage | payload | pipeline | 202 | 7 (6 to 7) | 0 (0) | channels 202 | 202/202 |
| damage | payload | swarm | 78 | 7 (6 to 9) | 76 (76) | channels 76, fit 2 | 78/78 |
| damage | reversed_motor | pipeline | 214 | 6 (6 to 7) | 0 (0) | channels 213, fit 1 | 211/214 |
| damage | reversed_motor | swarm | 82 | 7 (4 to 9) | 71 (71) | channels 73, fit 9 | 81/82 |
| damage | tool | pipeline | 241 | 6 (6 to 7) | 0 (0) | channels 241 | 238/241 |
| damage | tool | swarm | 79 | 7 (4 to 9) | 71 (71) | channels 71, fit 8 | 78/79 |
| faults | bad_llm | pipeline | 231 | 7 (7 to 8) | 0 (0) | fit 231 | 0/231 |
| faults | bad_llm | swarm | 65 | 7 (5 to 8) | 60 (60) | channels 60, fit 5 | 65/65 |
| faults | modeler_crash | pipeline | 2 | 6 (6 to 6) | 0 (0) | channels 2 | 2/2 |
| faults | modeler_crash | swarm | 77 | 7 (5 to 8) | 70 (70) | channels 72, fit 5 | 77/77 |
| faults | noisy_channel | pipeline | 327 | 7 (6 to 7) | 0 (0) | channels 301, fit 26 | 267/327 |
| faults | noisy_channel | swarm | 95 | 7 (3 to 9) | 68 (68) | channels 67, fit 27, prior 1 | 68/95 |
| faults | none | pipeline | 262 | 7 (6 to 7) | 0 (0) | channels 262 | 262/262 |
| faults | none | swarm | 83 | 7 (5 to 8) | 76 (76) | channels 78, fit 5 | 83/83 |
| faults | wrong_finding | pipeline | 197 | 6 (6 to 7) | 0 (0) | fit 195, channels 2 | 17/197 |
| faults | wrong_finding | swarm | 88 | 6 (5 to 7) | 3 (3) | channels 78, fit 8, prior 2 | 88/88 |
| noise | 1 mm | pipeline | 126 | 7 (6 to 7) | 0 (0) | channels 126 | 126/126 |
| noise | 1 mm | swarm | 60 | 7 (5 to 8) | 57 (57) | channels 57, fit 3 | 60/60 |
| noise | 10 mm | pipeline | 93 | 6 (6 to 7) | 0 (0) | channels 58, fit 35 | 16/93 |
| noise | 10 mm | swarm | 38 | 7 (4 to 8) | 22 (22) | fit 20, channels 16, prior 2 | 25/38 |
| noise | 2 mm | pipeline | 126 | 6 (6 to 7) | 0 (0) | channels 126 | 126/126 |
| noise | 2 mm | swarm | 38 | 7 (7 to 8) | 38 (38) | channels 38 | 38/38 |
| noise | 5 mm | pipeline | 121 | 7 (6 to 7) | 0 (0) | channels 106, fit 15 | 121/121 |
| noise | 5 mm | swarm | 36 | 7 (7 to 8) | 36 (36) | channels 32, fit 4 | 36/36 |

## Final champion of each run

| experiment | setting | condition | champions | agent types | competing (disagreed) | won | structure right |
| --- | --- | --- | --- | --- | --- | --- | --- |
| damage | bent_axis | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | bent_axis | swarm | 20 | 8 (6 to 9) | 19 (19) | channels 20 | 20/20 |
| damage | locked_joint | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 17, fit 3 | 5/20 |
| damage | locked_joint | swarm | 20 | 8 (6 to 9) | 11 (11) | channels 17, fit 2, prior 1 | 16/20 |
| damage | long_link | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | long_link | swarm | 20 | 8 (6 to 9) | 19 (19) | channels 19, fit 1 | 20/20 |
| damage | payload | pipeline | 20 | 7 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | payload | swarm | 20 | 8 (6 to 9) | 19 (19) | channels 19, fit 1 | 20/20 |
| damage | reversed_motor | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | reversed_motor | swarm | 20 | 8 (4 to 9) | 16 (16) | channels 18, fit 2 | 19/20 |
| damage | tool | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| damage | tool | swarm | 20 | 8 (5 to 9) | 17 (17) | channels 17, fit 3 | 19/20 |
| faults | bad_llm | pipeline | 40 | 7 (7 to 8) | 0 (0) | fit 40 | 0/40 |
| faults | bad_llm | swarm | 40 | 7 (6 to 8) | 38 (38) | channels 38, fit 2 | 40/40 |
| faults | modeler_crash | pipeline | 2 | 6 (6 to 6) | 0 (0) | channels 2 | 2/2 |
| faults | modeler_crash | swarm | 40 | 7 (6 to 8) | 39 (39) | channels 40 | 40/40 |
| faults | noisy_channel | pipeline | 40 | 6 (6 to 7) | 0 (0) | channels 35, fit 5 | 29/40 |
| faults | noisy_channel | swarm | 39 | 7 (3 to 9) | 29 (29) | channels 28, fit 10, prior 1 | 28/39 |
| faults | none | pipeline | 40 | 6 (6 to 7) | 0 (0) | channels 40 | 40/40 |
| faults | none | swarm | 40 | 7 (6 to 8) | 39 (39) | channels 40 | 40/40 |
| faults | wrong_finding | pipeline | 40 | 6 (6 to 7) | 0 (0) | fit 40 | 4/40 |
| faults | wrong_finding | swarm | 40 | 6 (6 to 7) | 1 (1) | channels 37, fit 2, prior 1 | 40/40 |
| noise | 1 mm | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| noise | 1 mm | swarm | 20 | 8 (7 to 8) | 20 (20) | channels 20 | 20/20 |
| noise | 10 mm | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 11, fit 9 | 4/20 |
| noise | 10 mm | swarm | 20 | 7 (4 to 8) | 12 (12) | fit 11, channels 7, prior 2 | 13/20 |
| noise | 2 mm | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 20 | 20/20 |
| noise | 2 mm | swarm | 20 | 7 (7 to 8) | 20 (20) | channels 20 | 20/20 |
| noise | 5 mm | pipeline | 20 | 6 (6 to 7) | 0 (0) | channels 18, fit 2 | 20/20 |
| noise | 5 mm | swarm | 20 | 7 (7 to 8) | 20 (20) | channels 18, fit 2 | 20/20 |
