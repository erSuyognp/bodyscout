# Provenance of crowned champions (120 boards, 490 champions)

Agent types: distinct agent types among a champion's ancestors, median (range). Competing: champions whose model was fit with hypotheses from two or more sources, and how many of those had sources whose first structures disagreed. Won: whose proposal the champion's structure came from (fit = no hypothesis had it). Pipeline authors are stages of one orchestrator, not independent agents.

## Every champion

| experiment | setting | condition | champions | agent types | competing (disagreed) | won | structure right |
| --- | --- | --- | --- | --- | --- | --- | --- |
| damage | long_link | pipeline | 47 | 6 (6 to 7) | 0 (0) | channels 47 | 47/47 |
| damage | long_link | swarm | 18 | 8 (4 to 9) | 16 (16) | channels 16, fit 2 | 18/18 |
| faults | bad_llm | pipeline | 44 | 7 (7 to 8) | 0 (0) | fit 44 | 0/44 |
| faults | bad_llm | swarm | 14 | 7 (4 to 7) | 13 (13) | channels 13, fit 1 | 14/14 |
| faults | modeler_crash | swarm | 15 | 7 (4 to 8) | 13 (13) | channels 13, fit 2 | 15/15 |
| faults | noisy_channel | pipeline | 56 | 7 (6 to 7) | 0 (0) | channels 43, fit 13 | 21/56 |
| faults | noisy_channel | swarm | 24 | 7 (3 to 10) | 11 (11) | fit 15, channels 9 | 7/24 |
| faults | none | pipeline | 58 | 6 (6 to 7) | 0 (0) | channels 58 | 58/58 |
| faults | none | swarm | 15 | 7 (5 to 8) | 13 (13) | channels 13, fit 2 | 15/15 |
| faults | wrong_finding | pipeline | 48 | 6 (6 to 7) | 0 (0) | fit 48 | 0/48 |
| faults | wrong_finding | swarm | 18 | 6 (6 to 7) | 0 (0) | channels 18 | 18/18 |
| noise | 1 mm | pipeline | 29 | 7 (6 to 7) | 0 (0) | channels 29 | 29/29 |
| noise | 1 mm | swarm | 8 | 7 (7 to 8) | 8 (8) | channels 8 | 8/8 |
| noise | 10 mm | pipeline | 21 | 7 (6 to 7) | 0 (0) | channels 20, fit 1 | 0/21 |
| noise | 10 mm | swarm | 7 | 6 (4 to 7) | 1 (1) | fit 6, channels 1 | 3/7 |
| noise | 2 mm | pipeline | 27 | 7 (6 to 7) | 0 (0) | channels 27 | 27/27 |
| noise | 2 mm | swarm | 8 | 7 (7 to 8) | 8 (8) | channels 8 | 8/8 |
| noise | 5 mm | pipeline | 26 | 7 (6 to 7) | 0 (0) | channels 26 | 26/26 |
| noise | 5 mm | swarm | 7 | 7 (7 to 7) | 7 (7) | channels 7 | 7/7 |

## Final champion of each run

| experiment | setting | condition | champions | agent types | competing (disagreed) | won | structure right |
| --- | --- | --- | --- | --- | --- | --- | --- |
| damage | long_link | pipeline | 4 | 6 (6 to 7) | 0 (0) | channels 4 | 4/4 |
| damage | long_link | swarm | 4 | 9 (8 to 9) | 4 (4) | channels 4 | 4/4 |
| faults | bad_llm | pipeline | 8 | 7 (7 to 8) | 0 (0) | fit 8 | 0/8 |
| faults | bad_llm | swarm | 8 | 7 (7 to 7) | 8 (8) | channels 8 | 8/8 |
| faults | modeler_crash | swarm | 8 | 7 (7 to 8) | 8 (8) | channels 8 | 8/8 |
| faults | noisy_channel | pipeline | 8 | 6 (6 to 7) | 0 (0) | channels 6, fit 2 | 2/8 |
| faults | noisy_channel | swarm | 8 | 6 (3 to 10) | 3 (3) | fit 5, channels 3 | 2/8 |
| faults | none | pipeline | 8 | 6 (6 to 7) | 0 (0) | channels 8 | 8/8 |
| faults | none | swarm | 8 | 7 (7 to 8) | 8 (8) | channels 8 | 8/8 |
| faults | wrong_finding | pipeline | 8 | 6 (6 to 7) | 0 (0) | fit 8 | 0/8 |
| faults | wrong_finding | swarm | 8 | 6 (6 to 7) | 0 (0) | channels 8 | 8/8 |
| noise | 1 mm | pipeline | 4 | 6 (6 to 7) | 0 (0) | channels 4 | 4/4 |
| noise | 1 mm | swarm | 4 | 8 (7 to 8) | 4 (4) | channels 4 | 4/4 |
| noise | 10 mm | pipeline | 4 | 6 (6 to 7) | 0 (0) | channels 4 | 0/4 |
| noise | 10 mm | swarm | 4 | 6 (6 to 7) | 1 (1) | fit 3, channels 1 | 2/4 |
| noise | 2 mm | pipeline | 4 | 6 (6 to 6) | 0 (0) | channels 4 | 4/4 |
| noise | 2 mm | swarm | 4 | 7 (7 to 8) | 4 (4) | channels 4 | 4/4 |
| noise | 5 mm | pipeline | 4 | 6 (6 to 6) | 0 (0) | channels 4 | 4/4 |
| noise | 5 mm | swarm | 4 | 7 (7 to 7) | 4 (4) | channels 4 | 4/4 |
