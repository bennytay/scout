# What Auki Labs cares about (relevance rubric)

Edit this file to change what the system considers relevant. No code changes are needed.

Auki Labs builds the **posemesh**, a decentralized network for spatial computing. It lets devices
(phones, AR glasses, robots) share a common understanding of physical space: where they are, what is
around them, and how to find things. Auki's product line covers visual positioning, shared spatial maps,
and machine perception for robots working in retail and other real-world venues.

Score `auki_relevance` from 0 to 1:

- **0.9–1.0: core.** Visual positioning / relocalization, shared or persistent spatial maps,
  multi-device or multi-robot shared spatial understanding, collaborative SLAM, spatial anchors,
  privacy-preserving or decentralized mapping, machine perception for robots in indoor venues (retail, warehouses).
- **0.7–0.9: strongly adjacent.** SLAM and 3D reconstruction in general, scene graphs, semantic mapping,
  embodied navigation, robot foundation models that consume spatial context, fleet coordination,
  AR/robotics convergence, major humanoid/robot platform launches that will need spatial infrastructure.
- **0.4–0.7: useful context.** General manipulation/locomotion/VLA research, robotics datasets and
  benchmarks, simulation, hardware, notable industry news.
- **0.0–0.4: peripheral.** Robotics-adjacent ML with no spatial or embodied angle, pure theory, hype with
  no substance.

The `auki_relevance_reason` is one concrete sentence a busy founder would find useful, e.g.
"Shows multi-robot map merging without a central server, the same problem posemesh domains solve."
Don't write generic praise like "This is an important paper."
