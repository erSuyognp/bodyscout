# Knockout: one agent type removed at motion 24 (20 unknown bodies: arm, gantry, scara, telescope x 5 seeds)

| removed | structure right | median reach at 64 motions, mm | change vs full, mm | runs with no model | validator disagreements |
| --- | --- | --- | --- | --- | --- |
| full collective | 20/20 | 1.7 |  | 0 | 0 |
| no findings hypothesizer | 20/20 | 1.4 | -0.2 | 0 | 0 |
| no prior hypothesizer | 20/20 | 1.4 | -0.2 | 0 | 0 |
| no library hypothesizer | 20/20 | 1.4 | -0.2 | 0 | 0 |
| one validator lost | 20/20 | 1.4 | -0.3 | 0 | 0 |
| one explorer lost | 20/20 | 1.4 | -0.3 | 0 | 0 |
| no monitor | 20/20 | 1.4 | -0.2 | 0 | 0 |
| every hypothesizer lost | 20/20 | 1.6 | -0.0 | 0 | 0 |
| one chain modeler lost | 20/20 | 1.6 | -0.1 | 0 | 0 |
| bent pose channel agents lost | 20/20 | 1.6 | -0.0 | 0 | 0 |
| review agent lost | 20/20 | 1.5 | -0.2 | 0 | 0 |

LLM hypothesizers were off (no --llm), so their knockouts were not run. The library hypothesizer has an empty library in these runs, so removing it is a no-op control.
