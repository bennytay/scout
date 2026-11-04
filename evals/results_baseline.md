# Eval results (2026-11-05)

- LLM: `fake (keyword heuristic baseline)` · embeddings: `fake (hashed BoW)`
- 56 hand-labelled items, 21 search queries, 5 author queries · enrichment cost $0.0 · failures 0

| Metric | Value |
|---|---|
| topics · primary_acc | 46% |
| topics · any_overlap_acc | 70% |
| topics · micro_precision | 44% |
| topics · micro_recall | 58% |
| topics · micro_f1 | 50% |
| relevance · band accuracy | 38% |
| search · p@5 | 0.72 |
| search · r@5 | 0.72 |
| search · mrr | 1.00 |
| search · hit@1 | 1.00 |
| author filter · precision | 87% |
| author filter · recall | 100% |

Relevance confusion (rows = labelled, cols = predicted):

| | high | mid | low |
|---|---|---|---|
| **high** | 9 | 0 | 2 |
| **mid** | 2 | 2 | 26 |
| **low** | 4 | 1 | 10 |

Per-query:

| query | P@5 | RR |
|---|---|---|
| visual relocalization in changing environments | 0.20 | 1.00 |
| 3D scene graphs as long-term robot memory | 0.75 | 1.00 |
| humanoid loco-manipulation | 0.67 | 1.00 |
| world action models that predict video and actions | 0.60 | 1.00 |
| making VLA inference faster and smaller | 0.50 | 1.00 |
| coordinating multiple robots | 0.40 | 1.00 |
| dexterous robot hands | 0.50 | 1.00 |
| learning manipulation from human videos | 0.75 | 1.00 |
| localization against a floor plan | 1.00 | 1.00 |
| structure from motion reconstruction | 1.00 | 1.00 |
| benchmarks for robot learning | 0.25 | 1.00 |
| teleoperation and demonstration data collection | 0.67 | 1.00 |
| safe navigation for legged robots | 1.00 | 1.00 |
| swarm robots reality gap | 1.00 | 1.00 |
| feature matching for SLAM and visual localization | 0.50 | 1.00 |
| autonomous driving | 0.33 | 1.00 |
| tendon-driven hand actuation | 1.00 | 1.00 |
| inverse kinematics for robot arms | 1.00 | 1.00 |
| aerial localization with 3D city maps | 1.00 | 1.00 |
| underwater vehicle missions | 1.00 | 1.00 |
| data-efficient imitation learning | 1.00 | 1.00 |
