# BodyScout: 3 minute talk track

Spoken text is under 440 words, roughly 145 words a minute. Every number is from `results/slide_numbers.md` or
`results/summary.md`; the caveats are part of the script, not the backup slides.

---

**Slide 1, the mystery (0:00 to 0:15)**

Here is a robot. Unlabeled channels, a fingertip we can see, no model file. Arm, gantry, SCARA, telescoping boom,
wired in any order. What is it, and can you make it reach a point?

**Slide 2, the swarm figures it out (0:15 to 0:45)**

BodyScout doesn't ask. Two agents per channel sweep it from different poses; a channel counts only when they agree.
Hypothesizers propose structures, modelers fit them, two validators crown one by held-out error. On twenty robots
we never designed against: full structure right twenty out of twenty, reaching to 1.5 millimetres. A single agent
searching blind got five. But a single agent that probes channels, and a fixed pipeline, also get twenty. So probing
works; whether the swarm is needed comes later.

**Slide 3, secret damage (0:45 to 1:15)**

Now we break it mid run. The alarm went off in 97 of 120 runs. Planning pauses, the swarm relearns. In the cube task
it placed 20 of 20 before and 20 of 20 after; the single agent dropped to 4. Caveat: the pipeline, same parts in a
fixed order, detects 95 of 120 and relearns faster: a trusted model in 112 of 120 runs, ours in 59. Damage handling
comes from the monitor and validators, not from the collective.

**Slide 4, scale (1:15 to 1:35)**

1938 runs: four body families, four real arms with shuffled channels, six damage kinds, four noise levels. At 10
millimetres of camera noise it ends at 9.1; the baselines at 31 to 50. It refuses every out-of-reach target.

**Slide 5, is the swarm necessary? (1:35 to 2:10)**

On a clean body they tie. Under faults, only the collective stays under 10 millimetres on all four: swarm four of
four, single_probe three, pipeline one, single none. A channel agent reports the wrong joint type: the swarm stays at
1.5, the pipeline goes to 41.4. A modeler crashes: the pipeline has no model in 18 of 20. single_probe has no LLM
stage, so the bad-LLM fault cannot touch it. We designed these fixes after a preview, so these numbers are from new
seeds, 101 to 105.

**Slide 6, failures we found (2:10 to 2:40)**

A sensor that is wrong every time: the swarm ends at 5.1 millimetres, the baselines at 3.7. On arms with nothing
to discover, a single agent wins, 1.5 against 2.4. It is expensive: the collective spends about a
minute and a half of CPU per robot, 91.5 seconds against 5.8 for the pipeline, to stay right when a part lies or
breaks. The pipeline is cheaper, wrong in those cases, and better when a sensor is noisy.

**Slide 7, how it works (2:40 to 2:50)**

Agents on one evidence board, every result traceable to raw motions. Pravesh added dynamics and vision agents
without redesigning anything.

**Slide 8, what is next (2:50 to 3:00)**

Real servos, hanging humanoids, a ScienceClaw skill other teams can call, and self-driving labs, where nobody hands
you the model either. Thank you.
