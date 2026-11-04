# Eval results (2026-11-05)

- LLM: `anthropic:claude-haiku-5-5` · embeddings: `local:BAAI/bge-small-en-v1.5`
- 56 hand-labelled items, 21 search queries, 5 author queries · enrichment cost $0.0377 · failures 0

| Metric | Value |
|---|---|
| topics · primary_acc | 91% |
| topics · any_overlap_acc | 96% |
| topics · micro_precision | 68% |
| topics · micro_recall | 89% |
| topics · micro_f1 | 77% |
| relevance · band accuracy | 75% |
| search · p@5 | 0.87 |
| search · r@5 | 0.87 |
| search · mrr | 0.98 |
| search · hit@1 | 0.95 |
| author filter · precision | 87% |
| author filter · recall | 100% |

Relevance confusion (rows = labelled, cols = predicted):

| | high | mid | low |
|---|---|---|---|
| **high** | 10 | 1 | 0 |
| **mid** | 5 | 25 | 0 |
| **low** | 0 | 8 | 7 |

Per-query:

| query | P@5 | RR |
|---|---|---|
| visual relocalization in changing environments | 0.80 | 1.00 |
| 3D scene graphs as long-term robot memory | 1.00 | 1.00 |
| humanoid loco-manipulation | 1.00 | 1.00 |
| world action models that predict video and actions | 0.80 | 1.00 |
| making VLA inference faster and smaller | 0.50 | 1.00 |
| coordinating multiple robots | 0.60 | 1.00 |
| dexterous robot hands | 1.00 | 1.00 |
| learning manipulation from human videos | 1.00 | 1.00 |
| localization against a floor plan | 1.00 | 1.00 |
| structure from motion reconstruction | 1.00 | 1.00 |
| benchmarks for robot learning | 0.25 | 1.00 |
| teleoperation and demonstration data collection | 1.00 | 0.50 |
| safe navigation for legged robots | 1.00 | 1.00 |
| swarm robots reality gap | 1.00 | 1.00 |
| feature matching for SLAM and visual localization | 1.00 | 1.00 |
| autonomous driving | 0.67 | 1.00 |
| tendon-driven hand actuation | 1.00 | 1.00 |
| inverse kinematics for robot arms | 1.00 | 1.00 |
| aerial localization with 3D city maps | 1.00 | 1.00 |
| underwater vehicle missions | 1.00 | 1.00 |
| data-efficient imitation learning | 0.67 | 1.00 |
