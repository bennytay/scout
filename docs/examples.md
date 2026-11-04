# Example questions and real answers

_Generated 2026-11-05 01:50 by `scripts/examples.py` against the live database (LLM `anthropic:claude-haiku-5-5`, embeddings `local:BAAI/bge-small-en-v1.5`). Re-run any time._

## /ask What's new this week in visual localization or relocalization?

This week's visual localization and relocalization papers are mostly from 2026-10-30 to 2026-11-03. The most directly relevant:

- **Ray-SCR** lets one scene map localize pinhole, fisheye, and omnidirectional cameras [7]. Cross-camera relocalization against a single persistent map is a core posemesh problem.
- **PGGT-Loc** estimates 6-DoF pose from a single image by grounding it to existing planar map primitives, without a dedicated localization map [5]. This could reduce the cost of mapping for posemesh-style deployments.
- **RingMatch** does wide-area ground-to-aerial localization over regions up to 400 m, using coarse-to-fine search and a verifier [3]. It targets outdoor aerial maps rather than indoor venues.
- **LoD-Loc v4** registers aerial images against a panoptic 3D map built from OpenStreetMap, DEMs, and LoD assets, and still works in sparse rural areas [1].
- **CoReMatch** is a real-time feature matcher that reports higher accuracy than Efficient LoFTR and more than 10x faster speed on embedded hardware [4]. Fast matching on edge devices supports the visual localization and SLAM that shared spatial understanding depends on.
- **PadLoc** localizes a sensor in a known floor plan without training, and a camera-only rig works on several construction-floor sessions [6]. It is single-device, but it is close to indoor visual positioning.

Two other papers are only tangential: MoSoLoco localizes people from a monocular camera per frame, with no shared map [2], and ReconSpatial benchmarks multi-view metric reasoning in vision-language models rather than mapping or relocalization [8].

1. [LoD-Loc v4: Towards Generalized Aerial Visual Localization via Panoptic LoD 3D Map Registration](https://arxiv.org/abs/2611.00704)
2. [MoSoLoco: Monocular 3D Human Localization through Visual Latent Features and Social Context](https://arxiv.org/abs/2611.03189)
3. [Beyond Local Refinement: Wide-Area Precise Cross-View Localization](https://arxiv.org/abs/2611.04759)
4. [CoReMatch: Recurrent Continuous Coordinate Refinement for Real-Time Robotic Feature Matching](https://arxiv.org/abs/2611.03932)
5. [PGGT-Loc: Primitive-Grounded Geometry Transformer for Feed-Forward Camera Localization](https://arxiv.org/abs/2610.41833)
6. [PadLoc: Training-Free Floor-Plan Localization by Sparse Geometric Matching](https://arxiv.org/abs/2611.05172)

## /ask Which recent papers build 3D scene graphs for robot memory?

Only one source, [1], directly involves a scene-graph memory for a robot. It is a diagnostic study of whether a fine-tuned vision-language model actually uses a scene-graph memory of a robot's route. It finds that text-delivered memory is used strongly (+30 points on route questions), while standard graph encoders lose information, and giving each node its own input token recovers 8.3 points [1]. This is adjacent to Auki's shared spatial maps, but it covers single-agent question answering, not multi-device localization [1].

The other papers use related but different memory representations:
- [6] maintains per-part physical beliefs in a "robot scene map" for articulated objects, but it is single-robot and not described as a scene graph [6].
- [8] builds a shared 3D voxel belief field for object search on a mobile humanoid, again single-robot [8].
- [2], [4], and [3] store spatial memory for reconstruction or world generation rather than robot task memory [2][4][3].

1. [Do Embodied VLMs Actually Use Their Scene-Graph Memory?](https://arxiv.org/abs/2611.02056)
2. [Mamba3R: Fixed-Capacity Selective State Memory for Long-Sequence 3D Reconstruction](https://arxiv.org/abs/2611.04221)
3. [L3G-World: Real-Time Infinite World Generation with Latent 3D Gaussian Memory](https://arxiv.org/abs/2610.40614)
4. [SceneBound: How Much Should a Streaming 3D Reconstruction Model Remember?](https://arxiv.org/abs/2611.00756)
5. [LucidLyra: Feed-Forward Generative 3D Scene Reconstruction and Joint Understanding via Multi-Task Distillation](https://arxiv.org/abs/2610.40495)
6. [PhysVLMM: Interaction-Conditioned Physical Belief Maps for Articulated Objects in Robot Scene Maps](https://arxiv.org/abs/2610.40539)

## /ask What are people releasing for humanoid whole-body control?

Recent releases cover several approaches to humanoid whole-body control, all as arXiv papers:

- **Model-based locomotion:** An online iLQR-MPC controller for push recovery on the Unitree G1, with a 500 Hz whole-body controller and no platform-specific policy training [1].
- **Precise manipulation:** Anchor 1 from Archon Robotics, a controller using sparse human motion references that reports 30% to 80% lower tracking error in the strictest real-world setting [2].
- **Motion tracking:** DiffWBC, a one-step diffusion controller with test-time steering and simulation-free failure detection, deployed on a Unitree G1 [3].
- **Tactile reflexes:** ReflexArc, which adds a 10 ms tactile withdrawal pathway to learned policies and cuts the first force peak by 34.1% on a G1 [4].
- **Compliance:** CompliantBot, a training framework that teaches humanoids to yield to pushes and pulls while resuming their tasks [5].
- **Mobile manipulation:** Pixel, a full-stack system built around a low-cost wheeled humanoid with a unified whole-body controller and robot-free human demonstrations [6].
- **Loco-manipulation:** HLO-AMP, a hierarchical framework using object-aware motion priors for bimanual pick-and-place on a G1 [7], and ReGATE, a visual-fusion controller for reactive humanoid-object interaction that still grasps when the camera is occluded [8].

For Auki, none of these papers addresses spatial mapping, localization, or shared multi-device understanding. They are useful background on where humanoid platforms are heading, which is the context in which spatial infrastructure like the posemesh would matter.

1. [Online iLQR-MPC with Whole-Body Control for Robust Humanoid Locomotion](https://arxiv.org/abs/2611.04204)
2. [Anchor 1: Precise and Stable Humanoid Control for Whole-Body Manipulation](https://arxiv.org/abs/2611.00193)
3. [DiffWBC: Unlocking Steerable General Humanoid Motion Tracking via One-Step Diffusion Whole-Body Control](https://arxiv.org/abs/2610.41354)
4. [ReflexArc: Bottom-Up Integration of Instantaneous Tactile Reflexes into Whole-Body Humanoid Control](https://arxiv.org/abs/2611.04424)
5. [CompliantBot: Learning Whole-Body Compliance across Task Interfaces for Humanoid Control](https://arxiv.org/abs/2611.01748)
6. [Pixel: A Co-Designed Full-Stack Robot System for Learning General-Purpose Mobile Manipulation](https://arxiv.org/abs/2611.03648)

## /ask Anything on multiple robots sharing a map?

None of the sources directly address multiple robots sharing a map. The closest is [4], CONSORT, which covers cooperative localization for multiple robots in GPS-denied settings and plans for localization uncertainty. That touches the shared spatial understanding problem posemesh targets, but the tests were marine and the work is about planning, not a shared map. [2] and [1] are adjacent: [2] keeps a line-of-sight relay chain connected, and [1] maintains connectivity using each agent's local sensor measurements, but neither involves maps or localization. [3], [5], [7], and [8] are fleet coordination work that either plans on a known map or assumes known poses. [6] is a purely analytical two-robot trajectory result.

1. [Haptic Shared Control for Multi-Robot Systems](https://arxiv.org/abs/2611.05027)
2. [Nested Field-of-View Barriers for Teleoperated Multi-Robot Relay Chains](https://arxiv.org/abs/2611.05074)
3. [Local Solution Repair for Multi-Agent Pickup and Delivery](https://arxiv.org/abs/2611.02090)
4. [CONSORT: Uncertainty-Constrained Multi-Robot Planning for Cooperative Localization in GPS-Denied Environments](https://arxiv.org/abs/2610.41235)
5. [Late Autumn: LLM Agents Specialize a General Multi-Robot Planner for One Warehouse](https://arxiv.org/abs/2611.02391)
6. [A complete analytical characterization of optimal collision-free motion for two robots](https://arxiv.org/abs/2610.41558)

## `search(query='vision-language-action', since='7d', limit=5)`

| # | item | type | topics | Auki relevance |
|---|---|---|---|---|
| 1 | [From Reasoning to Action: Consequence-Grounded Alignment for Vision-Language-Action Models](https://arxiv.org/abs/2610.39543) | paper | vla-foundation-models, manipulation | 0.45 |
| 2 | [RoboSeed: Multidimensional Evaluation of Vision-Language-Action and World-Action Models: C](https://arxiv.org/abs/2610.40026) | paper | vla-foundation-models, datasets-benchmarks | 0.45 |
| 3 | [HiFOR: Hierarchical Foresight with Action-Guided World Grounding for Vision-Language-Actio](https://arxiv.org/abs/2610.40373) | paper | vla-foundation-models, manipulation | 0.45 |
| 4 | [CalVLA: Shaping Native Confidence in Vision-Language-Action Policies with Outcome Supervis](https://arxiv.org/abs/2611.00394) | paper | vla-foundation-models, manipulation | 0.3 |
| 5 | [OpenFlyV2: An onboard vision-language-action model for aerial perception and navigation](https://arxiv.org/abs/2610.39287) | paper | vla-foundation-models, locomotion, sim2real | 0.6 |

## `search(topic='slam-spatial-mapping', min_relevance=0.7, limit=5)`

| # | item | type | topics | Auki relevance |
|---|---|---|---|---|
| 1 | [PadLoc: Training-Free Floor-Plan Localization by Sparse Geometric Matching](https://arxiv.org/abs/2611.05172) | paper | slam-spatial-mapping, perception | 0.8 |
| 2 | [Sparse Anchors for Visual Multi-Session Registration in Changing Environments](https://arxiv.org/abs/2611.05084) | paper | slam-spatial-mapping, perception | 0.92 |
| 3 | [Beyond Local Refinement: Wide-Area Precise Cross-View Localization](https://arxiv.org/abs/2611.04759) | paper | slam-spatial-mapping, perception | 0.8 |
| 4 | [EndoS3:Endoscopic Semantic Splatting SLAM](https://arxiv.org/abs/2611.04358) | paper | slam-spatial-mapping, datasets-benchmarks | 0.72 |
| 5 | [Mamba3R: Fixed-Capacity Selective State Memory for Long-Sequence 3D Reconstruction](https://arxiv.org/abs/2611.04221) | paper | slam-spatial-mapping, perception | 0.8 |

## `search(type='repo', topic='manipulation', limit=5)`

| # | item | type | topics | Auki relevance |
|---|---|---|---|---|

## `trending(days=7)`

| item | sources | score |
|---|---|---|
| [Democratizing Robot-Use Agents: A Unified Harness with Open Models](https://arxiv.org/abs/2611.01560) | alphaxiv, arxiv, huggingface | 10.88 |
| [DreamX: Video Diffusion Model is a Universal Latent Action Learner](https://arxiv.org/abs/2611.05377) | alphaxiv, arxiv, huggingface | 9.14 |
| [RoboColosseum: Evaluating Physical Intelligence at Scale In-The-Wild](https://arxiv.org/abs/2611.02497) | alphaxiv, arxiv, huggingface | 8.68 |
| [Show HN: HackerBooks – HackerTube, but for books mentioned on HN](https://hackerbooks.org) | hackernews | 7.62 |
| [Stringman, an $800 open-source room scale gripper robot](https://neufangled.com) | hackernews | 7.51 |
