# Dynamics change detection

Damage at motion 48: payload_dyn (+0.35 kg at the tip) or weak_motor (one joint, kp x 0.5). Watch window after damage: 40 motions. Body type unknown to the swarm. Identical swarms; only the monitor differs. A shape sentinel costs 1 motion, a dynamics sentinel (25 samples at 10 ms) costs 0.5.

## In sample

Bodies: arm1, arm2, arm3, scara1, scara2. LLM hypothesizers: off (deterministic runs).

### Detection

| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |
| --- | --- | --- | --- | --- | --- | --- |
| payload_dyn | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| payload_dyn | DynamicsMonitor | 4/5 | 13.0 | 0 | 4/5 | 3/5 |
| weak_motor | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| weak_motor | DynamicsMonitor | 2/5 | 15.0 | 0 | 2/5 | n/a |

### Every run

| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm1 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm1 | 350 g payload in the gripper (dynamic) | dynamics | 9.0 | payload | 0.341 | n/a | 0 |
| arm1 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm1 | motor 2 lost half its stiffness | dynamics | 9.0 | weak motor 2 (truth 2) | n/a | 0.47 | 0 |
| arm2 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm2 | 350 g payload in the gripper (dynamic) | dynamics | 21.0 | payload | 0.347 | n/a | 0 |
| arm2 | motor 4 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm2 | motor 4 lost half its stiffness | dynamics | 21.0 | weak motor 4 (truth 4) | n/a | 0.49 | 0 |
| arm3 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm3 | 350 g payload in the gripper (dynamic) | dynamics | 17.0 | payload | 0.474 | n/a | 0 |
| arm3 | motor 4 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm3 | motor 4 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara1 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara1 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.348 | n/a | 0 |
| scara1 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara1 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara2 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara2 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara2 | motor 3 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara2 | motor 3 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |

### Tip path error on fast moves, before damage (vs noise free truth)

| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |
| --- | --- | --- | --- | --- |
| arm1 | 234.6 | 6.5 | 0.400 | 0.309 |
| arm2 | 265.4 | 7.5 | 0.199 | 0.207 |
| arm3 | 265.9 | 14.4 | 0.642 | 0.205 |
| scara1 | 177.4 | 4.3 | 0.277 | 0.309 |
| scara2 | 124.9 | 2.0 | 0.207 | 0.207 |

## Out of sample

New bodies with seeds no experiment or test had used. DynamicsMonitor and fit settings frozen at their committed values; nothing was tuned for or after these runs.
Bodies: arm101, arm102, arm103, arm104, arm105, scara101, scara102, scara103, telescope101, telescope102. LLM hypothesizers: off (deterministic runs).

### Detection

| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |
| --- | --- | --- | --- | --- | --- | --- |
| payload_dyn | shape Monitor | 0/10 | n/a | 0 | does not name causes | n/a |
| payload_dyn | DynamicsMonitor | 4/10 | 11.0 | 0 | 4/10 | 3/10 |
| weak_motor | shape Monitor | 0/10 | n/a | 0 | does not name causes | n/a |
| weak_motor | DynamicsMonitor | 4/10 | 21.0 | 0 | 4/10 | n/a |

### Every run

| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm102 | 350 g payload in the gripper (dynamic) | dynamics | 21.0 | payload | 0.345 | n/a | 0 |
| arm102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm102 | motor 2 lost half its stiffness | dynamics | 21.0 | weak motor 2 (truth 2) | n/a | 0.51 | 0 |
| arm103 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm103 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm103 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm103 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm104 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm104 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm104 | motor 3 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm104 | motor 3 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm105 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm105 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm105 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm105 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara102 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.342 | n/a | 0 |
| scara102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara102 | motor 2 lost half its stiffness | dynamics | 1.0 | weak motor 2 (truth 2) | n/a | 0.49 | 0 |
| scara103 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara103 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.550 | n/a | 0 |
| scara103 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara103 | motor 2 lost half its stiffness | dynamics | 25.5 | weak motor 2 (truth 2) | n/a | 0.49 | 0 |
| telescope101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| telescope101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| telescope101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| telescope102 | 350 g payload in the gripper (dynamic) | dynamics | 21.0 | payload | 0.418 | n/a | 0 |
| telescope102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| telescope102 | motor 2 lost half its stiffness | dynamics | 21.0 | weak motor 2 (truth 2) | n/a | 0.48 | 0 |

### Tip path error on fast moves, before damage (vs noise free truth)

| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |
| --- | --- | --- | --- | --- |
| arm101 | 33.9 | 2.7 | 0.078 | 0.103 |
| arm102 | 182.0 | 6.7 | 0.172 | 0.105 |
| arm103 | no dynamics model by motion 48 | n/a | n/a | n/a |
| arm104 | no dynamics model by motion 48 | n/a | n/a | n/a |
| arm105 | 91.1 | 1.6 | 0.000 | 0.353 |
| scara101 | 140.1 | 2.6 | 0.260 | 0.103 |
| scara102 | 137.5 | 2.4 | 0.101 | 0.105 |
| scara103 | 167.4 | 3.2 | 0.044 | 0.066 |
| telescope101 | 127.6 | 4.4 | 0.192 | 0.103 |
| telescope102 | 163.7 | 3.4 | 0.214 | 0.105 |

### In sample vs out of sample

| metric | in sample | out of sample |
| --- | --- | --- |
| payload_dyn, shape Monitor: detected | 0/5 | 0/10 |
| payload_dyn, shape Monitor: median motions to detect | n/a | n/a |
| payload_dyn, shape Monitor: false alarms before damage, per run | 0/5 runs | 0/10 runs |
| payload_dyn, DynamicsMonitor: detected | 4/5 | 4/10 |
| payload_dyn, DynamicsMonitor: median motions to detect | 13.0 | 11.0 |
| payload_dyn, DynamicsMonitor: false alarms before damage, per run | 0/5 runs | 0/10 runs |
| payload_dyn, DynamicsMonitor: cause named right | 4/5 | 4/10 |
| payload_dyn, DynamicsMonitor: added payload within 0.1 kg | 3/5 | 3/10 |
| weak_motor, shape Monitor: detected | 0/5 | 0/10 |
| weak_motor, shape Monitor: median motions to detect | n/a | n/a |
| weak_motor, shape Monitor: false alarms before damage, per run | 0/5 runs | 0/10 runs |
| weak_motor, DynamicsMonitor: detected | 2/5 | 4/10 |
| weak_motor, DynamicsMonitor: median motions to detect | 15.0 | 21.0 |
| weak_motor, DynamicsMonitor: false alarms before damage, per run | 0/5 runs | 0/10 runs |
| weak_motor, DynamicsMonitor: cause named right | 2/5 | 4/10 |

### Undamaged runs: false alarms over the whole run

Nothing is damaged; the run continues 40 motions past motion 48 exactly like a damaged run. Every alarm is false.

| body | shape Monitor alarms | DynamicsMonitor alarms | motions watched |
| --- | --- | --- | --- |
| arm106 | 0 | 0 | 91.0 |
| arm107 | 0 | 0 | 95.0 |
| scara104 | 0 | 0 | 92.0 |
| scara105 | 0 | 0 | 89.0 |
| telescope103 | 0 | 0 | 91.0 |

### What got worse out of sample

- payload_dyn, DynamicsMonitor: detected: 4/5 in sample, 4/10 out of sample
- payload_dyn, DynamicsMonitor: cause named right: 4/5 in sample, 4/10 out of sample
- payload_dyn, DynamicsMonitor: added payload within 0.1 kg: 3/5 in sample, 3/10 out of sample
- weak_motor, DynamicsMonitor: median motions to detect: 15.0 in sample, 21.0 out of sample

## With LLM hypothesizers

Same bodies, seeds, budgets and monitor settings as above; the only difference is that one LLM hypothesizer per provider with an API key joins every swarm. LLM answers vary, so these runs are not deterministic: rerunning gives somewhat different numbers.

### In sample, LLM on

Bodies: arm1, arm2, arm3, scara1, scara2. LLM hypothesizers: on (hyp-claude, hyp-gemini); 77 LLM hypotheses posted across 20 runs. Runs are not deterministic.

#### Detection

| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |
| --- | --- | --- | --- | --- | --- | --- |
| payload_dyn | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| payload_dyn | DynamicsMonitor | 3/5 | 9.0 | 0 | 3/5 | 2/5 |
| weak_motor | shape Monitor | 0/5 | n/a | 0 | does not name causes | n/a |
| weak_motor | DynamicsMonitor | 1/5 | 17.0 | 0 | 1/5 | n/a |

#### Every run

| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm1 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm1 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm1 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm1 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm2 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm2 | 350 g payload in the gripper (dynamic) | dynamics | 17.0 | payload | 0.307 | n/a | 0 |
| arm2 | motor 4 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm2 | motor 4 lost half its stiffness | dynamics | 17.0 | weak motor 4 (truth 4) | n/a | 0.52 | 0 |
| arm3 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm3 | 350 g payload in the gripper (dynamic) | dynamics | 9.0 | payload | 0.789 | n/a | 0 |
| arm3 | motor 4 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm3 | motor 4 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara1 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara1 | 350 g payload in the gripper (dynamic) | dynamics | 5.0 | payload | 0.350 | n/a | 0 |
| scara1 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara1 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara2 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara2 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara2 | motor 3 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara2 | motor 3 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |

#### Tip path error on fast moves, before damage (vs noise free truth)

| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |
| --- | --- | --- | --- | --- |
| arm1 | 234.4 | 3.7 | 0.312 | 0.309 |
| arm2 | 265.7 | 8.0 | 0.183 | 0.207 |
| arm3 | 266.0 | 14.7 | 0.702 | 0.205 |
| scara1 | 177.9 | 3.3 | 0.235 | 0.309 |
| scara2 | 124.8 | 2.5 | 0.251 | 0.207 |

### Out of sample, LLM on

Bodies: arm101, arm102, arm103, arm104, arm105, scara101, scara102, scara103, telescope101, telescope102. LLM hypothesizers: on (hyp-claude, hyp-gemini); 195 LLM hypotheses posted across 50 runs. Runs are not deterministic.

#### Detection

| damage | monitor | detected | median motions to detect | false alarms before damage | cause named right | added payload within 0.1 kg |
| --- | --- | --- | --- | --- | --- | --- |
| payload_dyn | shape Monitor | 0/10 | n/a | 0 | does not name causes | n/a |
| payload_dyn | DynamicsMonitor | 6/10 | 15.0 | 0 | 6/10 | 5/10 |
| weak_motor | shape Monitor | 0/10 | n/a | 0 | does not name causes | n/a |
| weak_motor | DynamicsMonitor | 6/10 | 15.0 | 0 | 6/10 | n/a |

#### Every run

| body | damage | monitor | detected after (motions) | cause named | added payload kg | kp ratio | false alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| arm101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| arm101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| arm102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm102 | 350 g payload in the gripper (dynamic) | dynamics | 25.0 | payload | 0.362 | n/a | 0 |
| arm102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm102 | motor 2 lost half its stiffness | dynamics | 25.0 | weak motor 2 (truth 2) | n/a | 0.51 | 0 |
| arm103 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm103 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.283 | n/a | 0 |
| arm103 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm103 | motor 2 lost half its stiffness | dynamics | 1.0 | weak motor 2 (truth 2) | n/a | 0.43 | 0 |
| arm104 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm104 | 350 g payload in the gripper (dynamic) | dynamics | 17.0 | payload | 0.314 | n/a | 0 |
| arm104 | motor 3 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm104 | motor 3 lost half its stiffness | dynamics | 17.0 | weak motor 3 (truth 3) | n/a | 0.50 | 0 |
| arm105 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| arm105 | 350 g payload in the gripper (dynamic) | dynamics | 13.0 | payload | 0.323 | n/a | 0 |
| arm105 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| arm105 | motor 1 lost half its stiffness | dynamics | 13.0 | weak motor 1 (truth 1) | n/a | 0.49 | 0 |
| scara101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| scara102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara102 | 350 g payload in the gripper (dynamic) | dynamics | 1.0 | payload | 0.326 | n/a | 0 |
| scara102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara102 | motor 2 lost half its stiffness | dynamics | 1.0 | weak motor 2 (truth 2) | n/a | 0.48 | 0 |
| scara103 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| scara103 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| scara103 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| scara103 | motor 2 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope101 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| telescope101 | 350 g payload in the gripper (dynamic) | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope101 | motor 1 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| telescope101 | motor 1 lost half its stiffness | dynamics | not detected | missed | n/a | n/a | 0 |
| telescope102 | 350 g payload in the gripper (dynamic) | shape | not detected | n/a | n/a | n/a | 0 |
| telescope102 | 350 g payload in the gripper (dynamic) | dynamics | 25.0 | payload | 0.451 | n/a | 0 |
| telescope102 | motor 2 lost half its stiffness | shape | not detected | n/a | n/a | n/a | 0 |
| telescope102 | motor 2 lost half its stiffness | dynamics | 25.0 | weak motor 2 (truth 2) | n/a | 0.48 | 0 |

#### Tip path error on fast moves, before damage (vs noise free truth)

| body | shape only, mm | learned dynamics, mm | learned payload kg | true payload kg |
| --- | --- | --- | --- | --- |
| arm101 | 33.8 | 2.6 | 0.065 | 0.103 |
| arm102 | 182.2 | 6.0 | 0.147 | 0.105 |
| arm103 | 212.9 | 5.2 | 0.097 | 0.066 |
| arm104 | 259.8 | 7.2 | 0.231 | 0.187 |
| arm105 | 91.4 | 2.1 | 0.348 | 0.353 |
| scara101 | 140.0 | 2.5 | 0.169 | 0.103 |
| scara102 | 137.7 | 1.8 | 0.109 | 0.105 |
| scara103 | 167.2 | 3.3 | 0.026 | 0.066 |
| telescope101 | 127.4 | 4.8 | 0.208 | 0.103 |
| telescope102 | 163.9 | 3.9 | 0.192 | 0.105 |

### LLM off vs LLM on

| metric | in sample: off | in sample: on | out of sample: off | out of sample: on |
| --- | --- | --- | --- | --- |
| payload_dyn, shape Monitor: detected | 0/5 | 0/5 | 0/10 | 0/10 |
| payload_dyn, shape Monitor: median motions to detect | n/a | n/a | n/a | n/a |
| payload_dyn, shape Monitor: false alarms before damage | 0/5 runs | 0/5 runs | 0/10 runs | 0/10 runs |
| payload_dyn, DynamicsMonitor: detected | 4/5 | 3/5 | 4/10 | 6/10 |
| payload_dyn, DynamicsMonitor: median motions to detect | 13.0 | 9.0 | 11.0 | 15.0 |
| payload_dyn, DynamicsMonitor: false alarms before damage | 0/5 runs | 0/5 runs | 0/10 runs | 0/10 runs |
| payload_dyn, DynamicsMonitor: cause named right | 4/5 | 3/5 | 4/10 | 6/10 |
| payload_dyn, DynamicsMonitor: added payload within 0.1 kg | 3/5 | 2/5 | 3/10 | 5/10 |
| weak_motor, shape Monitor: detected | 0/5 | 0/5 | 0/10 | 0/10 |
| weak_motor, shape Monitor: median motions to detect | n/a | n/a | n/a | n/a |
| weak_motor, shape Monitor: false alarms before damage | 0/5 runs | 0/5 runs | 0/10 runs | 0/10 runs |
| weak_motor, DynamicsMonitor: detected | 2/5 | 1/5 | 4/10 | 6/10 |
| weak_motor, DynamicsMonitor: median motions to detect | 15.0 | 17.0 | 21.0 | 15.0 |
| weak_motor, DynamicsMonitor: false alarms before damage | 0/5 runs | 0/5 runs | 0/10 runs | 0/10 runs |
| weak_motor, DynamicsMonitor: cause named right | 2/5 | 1/5 | 4/10 | 6/10 |
| shape Monitor: alarms on undamaged bodies |  |  | 0/5 runs | 0/5 runs |
| DynamicsMonitor: alarms on undamaged bodies |  |  | 0/5 runs | 0/5 runs |

### Where LLMs made it worse

- in sample, payload_dyn, DynamicsMonitor: detected: 4/5 with LLMs off, 3/5 with LLMs on
- out of sample, payload_dyn, DynamicsMonitor: median motions to detect: 11.0 with LLMs off, 15.0 with LLMs on
- in sample, payload_dyn, DynamicsMonitor: cause named right: 4/5 with LLMs off, 3/5 with LLMs on
- in sample, payload_dyn, DynamicsMonitor: added payload within 0.1 kg: 3/5 with LLMs off, 2/5 with LLMs on
- in sample, weak_motor, DynamicsMonitor: detected: 2/5 with LLMs off, 1/5 with LLMs on
- in sample, weak_motor, DynamicsMonitor: median motions to detect: 15.0 with LLMs off, 17.0 with LLMs on
- in sample, weak_motor, DynamicsMonitor: cause named right: 2/5 with LLMs off, 1/5 with LLMs on

Notes: the swarm gets one absolute reference, the servo datasheet (rotor inertia and velocity gain). Without it a payload in kilograms is unobservable from positions: scaling every mass, kp and damping together leaves every path unchanged. The added payload is estimated by refitting only the payload on the two sentinel trajectories that raised the alarm.

Tuning disclosure: the DynamicsMonitor's settings were changed once after a first run on the in sample bodies. That run used a median baseline, a 2x / +6 mm threshold and a 10 mm kinematic gate, and detected 4/10. The fixes: a baseline that one post damage sentinel cannot inflate (a real bug: arm2's 8 to 91 mm payload jump was missed), a threshold of max(1.5x, +2.5 mm), and a 15 mm kinematic gate (arm3's shape model sat at 11 mm, so it never fitted dynamics). The shape Monitor was not changed. The in sample numbers are in sample; the out of sample section is the honest test.
