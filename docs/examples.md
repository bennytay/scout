# Example questions and real answers

_Generated 2026-11-05 15:34 by `scripts/examples.py` against the live database (LLM `anthropic:claude-haiku-5-5`, embeddings `local:BAAI/bge-small-en-v1.5`). Re-run any time._

## @Scout What's new in humanoids this week, and who announced it?

This week's humanoid news in the provided sources (dated Nov 3–4, 2026):

- **Agility Robotics** completed its SPAC merger with Churchill Capital Corp XI. Its stock and warrants are expected to trade on Nasdaq on Nov 5 as AGLT and AGLTW [3].
- **Xiaomi**, as reported by CyberRobo, says its CyberOne 02 humanoids worked 8 consecutive hours sorting and placing parts alongside AMRs at a Xiaomi EV factory. The post gives no independent metrics or video [6]. This is the most relevant item for Auki, since multi-robot indoor deployments like this need shared spatial understanding, though the source doesn't address mapping or localization.
- **Unitree Robotics** announced support for RoboColosseum, a real-world robotics bench

1. [@UnitreeRobotics: Excited to support RoboColosseum, one of the largest in-the-wild real-world robotics benchmark project! Great to see…](https://x.com/UnitreeRobotics/status/2117996574584574130)
2. [@leggedrobotics: In our latest work @corl_conf, we present ADAPT: an end-to-end framework for interactive, text-conditioned humanoid…](https://x.com/leggedrobotics/status/2117564271249051665)
3. [@agilityrobotics: Agility Robotics has completed its business combination with Churchill Capital Corp XI. Our common stock and warrants…](https://x.com/agilityrobotics/status/2118097240791339141)
4. [@danielpmorton: Humanoid retargeting and IK in microseconds [no GPU required] Orders of magnitude speedups, with perfect contact…](https://x.com/danielpmorton/status/2118026028572680195)
5. [@lukas_m_ziegler: What a week in robotics. I summarized the most important news from the physical AI space. → Tesla is building Optimus…](https://x.com/lukas_m_ziegler/status/2117657514372194386)
6. [@CyberRobooo: A humanoid worker putting in an 8-hour shift. Xiaomi announced that its CyberOne 02 humanoid robots completed 8…](https://x.com/CyberRobooo/status/2117532860785795389)

## @Scout What did ETH's legged robotics people post about navigation, and is there code?

ETH's Robotic Systems Lab posted about **WayTrace**, a navigation system that takes a legged robot from web-map directions to real-world missions. Their post says an off-the-shelf VLM, an onboard trace model, and an RL locomotion policy completed 2.35 km of missions in Zurich, but it only gives the headline and points to a thread for details [3]. The WayTrace paper, by ETH authors Patel, Frey, Roth, and Hutter, reports missions of up to 1.37 km at about 1.1 m/s on a wheeled-legged robot, and about ten times fewer violations than point-goal baselines in simulation [2]. The 2.35 km and 1.37 km figures don't match, so check which is correct before citing either.

I found no code for WayTrace in the sources. The only ETH legged-robotics code release is **Terrain-Grounded Imagination** [1], which trains a Unitree G1 humanoid to cross stairs, gaps, and stepping stones. It's a locomotion method rather than a navigation system, and its repo is at github.com/leggedrobotics/terrain-grounded-imagination [1].

For Auki, WayTrace is adjacent to spatial understanding because it uses map and camera context outdoors, but neither WayTrace nor TGI addresses shared or persistent maps, which is the core posemesh problem [1][2].

1. [leggedrobotics/terrain-grounded-imagination: Terrain Grounded Imagination: a recipe for training humanoid locomotion on sparse and rough terrain through a world model with differentiable heightmap lookups.](https://github.com/leggedrobotics/terrain-grounded-imagination)
2. [WayTrace: A Map-to-Language-to-Trace Hierarchy for Embodied Urban Navigation](https://arxiv.org/abs/2611.05129)
3. [@leggedrobotics: Our new work WayTrace: an off-the-shelf VLM, an onboard trace model, and an RL policy take a robot from web-map…](https://x.com/leggedrobotics/status/2117991786983596126)
4. [A-Uta/StackChan_Minimal: Small AI companion robot firmware for M5Stack AtomS3R using local STT, LLM, and TTS services.](https://github.com/a-uta/stackchan_minimal)
5. [@IlirAliu_: An open robot eval initiative by @huggingface, @BitRobotNetwork, @eaic_sg and my good friend @DJiafei... Introducing…](https://x.com/IlirAliu_/status/2117993868306403356)
6. [Caging Vision-Language Navigation for Legged Robots via Barrier-Certified Safety Architecture](https://arxiv.org/abs/2611.04972)

## @Scout Any new vision-language-action models I can actually download?

The sources list several Hugging Face model pages that could be VLA or robot policy checkpoints, but none include a description, weights details, or license, so I can't confirm you can download them. The strongest candidates are:

- **FineART-VLA-subtask-midtrained** (LeRobot): described as a vision-language-action checkpoint, though its architecture and results are unconfirmed [7].
- **Jocasta-diff-VLA** (RobotLearningLab): described as a diffusion-based VLA model [1].
- **flux-3-action-so101** (Black Forest Labs): likely a robot action model for the SO-101 arm, but unverified [8].
- **v0.5-libero** (vernerobotics): probably a policy for the LIBERO manipulation benchmark, but its purpose is unconfirmed [2].

Others with unclear purpose include wall-oss-1.0-lite-robodojo [5], microduck-policies [6], SenseNova RoboRSI-27B Preview [3], and flux-3-action-base [4]. Check each repo's model card and license directly before relying on any of them.

For Auki, none of these sources show spatial mapping, localization, or multi-device features, so they are general embodied AI context rather than posemesh-relevant tools.

1. [RobotLearningLab/Jocasta-diff-VLA](https://huggingface.co/RobotLearningLab/Jocasta-diff-VLA)
2. [vernerobotics/v0.5-libero](https://huggingface.co/vernerobotics/v0.5-libero)
3. [sensenova/sensenova-roborsi-27b-preview](https://huggingface.co/sensenova/sensenova-roborsi-27b-preview)
4. [black-forest-labs/flux-3-action-base](https://huggingface.co/black-forest-labs/flux-3-action-base)
5. [x-square-robot/wall-oss-1.0-lite-robodojo](https://huggingface.co/x-square-robot/wall-oss-1.0-lite-robodojo)
6. [pollen-robotics/microduck-policies](https://huggingface.co/pollen-robotics/microduck-policies)

## @Scout Anything on robots sharing maps or relocalizing?

Yes, two sources are directly on point, though neither describes multiple robots sharing a live map.

- **Sparse Anchors for Visual Multi-Session Registration [2]** is the closest match. It registers a new robot recording session to a previously built visual reference map in changing environments, reaching 94.4% recall within 1m on HILTI26 construction-site data. For Auki, this is the kind of persistent-map relocalization that posemesh visual positioning depends on.
- **PadLoc [1]** localizes a moving sensor within a known floor plan using a compact state and no training. Reported results include 100% SR@1m on a static Bonn LiLocBench sequence. It relocalizes against a fixed map rather than one built collaboratively, but it targets the same indoor problem.
- **RingMatch [3]** handles ground-camera relocalization against aerial imagery over large outdoor regions. It is a weaker fit for Auki's indoor venue focus.

1. [PadLoc: Training-Free Floor-Plan Localization by Sparse Geometric Matching](https://arxiv.org/abs/2611.05172)
2. [Sparse Anchors for Visual Multi-Session Registration in Changing Environments](https://arxiv.org/abs/2611.05084)
3. [Beyond Local Refinement: Wide-Area Precise Cross-View Localization](https://arxiv.org/abs/2611.04759)
4. [EndoS3:Endoscopic Semantic Splatting SLAM](https://arxiv.org/abs/2611.04358)
5. [ReSMap: Recasting Satellite Priors for Robust and Accurate Online HD Map Construction](https://arxiv.org/abs/2611.04352)
6. [@leggedrobotics: Our new work WayTrace: an off-the-shelf VLM, an onboard trace model, and an RL policy take a robot from web-map…](https://x.com/leggedrobotics/status/2117991786983596126)

## `search(topic='humanoids', since='3d', limit=6)`

| # | item | type | topics | Auki relevance |
|---|---|---|---|---|
| 1 | [@CyberRobooo: Clone Robotics is no longer alone. Researchers at the University of Tokyo ar](https://x.com/CyberRobooo/status/2118153071435915381) | post | humanoids, hardware | 0.35 |
| 2 | [@CyberRobooo: Big step… Robots needs large-scale real-world testing. RoboColosseum is buil](https://x.com/CyberRobooo/status/2118124506158133748) | post | datasets-benchmarks, humanoids | 0.5 |
| 3 | [@agilityrobotics: Agility Robotics has completed its business combination with Churchill C](https://x.com/agilityrobotics/status/2118097240791339141) | post | humanoids, other | 0.4 |
| 4 | [@danielpmorton: Humanoid retargeting and IK in microseconds [no GPU required] Orders of ma](https://x.com/danielpmorton/status/2118026028572680195) | post | humanoids, manipulation | 0.3 |
| 5 | [@UnitreeRobotics: Excited to support RoboColosseum, one of the largest in-the-wild real-wo](https://x.com/UnitreeRobotics/status/2117996574584574130) | post | datasets-benchmarks, humanoids | 0.5 |
| 6 | [@MatthiasCaro: How do you train a humanoid on sparse terrain inside a world model? Terrain](https://x.com/MatthiasCaro/status/2117980846825390167) | post | humanoids, sim2real | 0.45 |

## `search(author='levine', limit=5)`

| # | item | type | topics | Auki relevance |
|---|---|---|---|---|
| 1 | [@svlevine: When running RL with prior data, a behavior constraint is important to trade of](https://x.com/svlevine/status/2118192498652991753) | post | other | 0.4 |
| 2 | [@svlevine: Distributional flow RL where we enforce Bellman consistency not just on the val](https://x.com/svlevine/status/2117824001565479007) | post | other | 0.25 |
| 3 | [GSBR: Geometric Support Behavior Regularization for Online RL](https://arxiv.org/abs/2611.05295) | paper | manipulation | 0.4 |
| 4 | [@svlevine: RL can help collect good data, whether you're doing BC or RL. It can also stack](https://x.com/svlevine/status/2117479583511716285) | post | manipulation, datasets-benchmarks | 0.5 |
| 5 | [Value Forcing: Aligning Return Distributions at All Noise Levels](https://arxiv.org/abs/2611.02160) | paper | other, datasets-benchmarks | 0.2 |

## `search(query='world model', type='post', limit=5)`

| # | item | type | topics | Auki relevance |
|---|---|---|---|---|
| 1 | [@IlirAliu_: What a 3D World Simulator!! 🤯 Play w/ the world model: [📌 GitHub below] A supe](https://x.com/IlirAliu_/status/2117903979770261925) | post | sim2real, vla-foundation-models | 0.5 |
| 2 | [@MatthiasCaro: How do you train a humanoid on sparse terrain inside a world model? Terrain](https://x.com/MatthiasCaro/status/2117980846825390167) | post | humanoids, sim2real | 0.45 |
| 3 | [@TheHumanoidHub: An AI model that helps transfer human motion, recorded with LiberSense Gl](https://x.com/TheHumanoidHub/status/2118046959613403552) | post | vla-foundation-models, manipulation | 0.45 |
| 4 | [@YunzhuLiYZ: A closer look at the interactive demo of our 3D World Simulator 🤖 You can con](https://x.com/YunzhuLiYZ/status/2117628499045609519) | post | sim2real, manipulation | 0.5 |
| 5 | [@CyberRobooo: CyberOne 02 is putting in shifts at Xiaomi’s EV factory. Its physical AI mod](https://x.com/CyberRobooo/status/2117617539392119162) | post | vla-foundation-models, manipulation | 0.55 |

## `/recent 3` (what's stored)

362 items stored; last 3 days: 256 papers, 39 posts, 30 models, 19 datasets, 10 articles, 8 repos

- [@CyberRobooo: A humanoid worker putting in an 8-hour shift. Xiaomi announced that its CyberOne 02 hu](https://x.com/CyberRobooo/status/2117532860785795389)
- [@BostonDynamics: We're thrilled to announce Stretch Gen 2, the next generation of our autonomous mob](https://x.com/BostonDynamics/status/2117663862564573240)
- [@mateoguaman: Kilometer-level navigation is super hard, especially in a city where a robot can encou](https://x.com/mateoguaman/status/2118013079547986228)
- [@leggedrobotics: Our new work WayTrace: an off-the-shelf VLM, an onboard trace model, and an RL poli](https://x.com/leggedrobotics/status/2117991786983596126)
- [@lukas_m_ziegler: 🚨 BREAKING: @tutorintel has raised $75M in Series B funding led by Andreessen Horo](https://x.com/lukas_m_ziegler/status/2117533011805716674)
- [@CyberRobooo: CyberOne 02 is putting in shifts at Xiaomi’s EV factory. Its physical AI model is now ](https://x.com/CyberRobooo/status/2117617539392119162)
- [@CyberRobooo: China’s humanoid worker on a South Korean auto injection line Korean company IL ran a ](https://x.com/CyberRobooo/status/2117977112913314184)
- [@CyberRobooo: Big step… Robots needs large-scale real-world testing. RoboColosseum is building a dis](https://x.com/CyberRobooo/status/2118124506158133748)
- [@CyberRobooo: Robots are starting to maintain their own memory centers. As AI scales, data centers a](https://x.com/CyberRobooo/status/2117952574339092719)
- [@IlirAliu_: What a 3D World Simulator!! 🤯 Play w/ the world model: [📌 GitHub below] A super-fast int](https://x.com/IlirAliu_/status/2117903979770261925)
