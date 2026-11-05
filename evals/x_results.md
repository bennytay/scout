# X signal eval

62 real posts from one live scan (12 radar, 50 discovery), 31 labelled keep by content alone. Judge: `claude-haiku-5-5`, cost $0.0097. Run 2026-11-05.

| stage | posts kept | precision | recall | F1 |
|---|---|---|---|---|
| gate only | 16 | 0.62 | 0.32 | 0.43 |
| gate + judge | 10 | 1.00 | 0.32 | 0.49 |
| gate + judge (radar) | 6 | 1.00 | 1.00 | 1.00 |
| gate + judge (discovery) | 4 | 1.00 | 0.16 | 0.28 |

Reading: the funnel is tuned for precision. Nothing kept was junk. Discovery misses are mostly arXiv-mirror bots
and paper summarisers with 0-5 likes: the paper exists, but nobody on X is discussing it yet, which is what
'X is the newsroom' filters for. Caveat: this snapshot was recorded minutes to hours after posting; live
discovery only judges posts 6h+ old, after likes accrue, so this recall is a lower bound.

Gate drop reasons: {'low_engagement': 45, 'spam': 1}. Judge labels: {'noise': 4, 'news': 8, 'discussion': 2, 'off_topic': 1, 'promo': 1}.

## Disagreements

- dropped but labelled keep: https://x.com/OWW/status/2118182608911638801 
- dropped but labelled keep: https://x.com/mengpaper/status/2118178901814018490 
- dropped but labelled keep: https://x.com/Elias_x86/status/2118169432149442938 
- dropped but labelled keep: https://x.com/OWW/status/2118146460046836082 
- dropped but labelled keep: https://x.com/SanemBuilds/status/2118143391754301741 
- dropped but labelled keep: https://x.com/OWW/status/2118141193334792404 
- dropped but labelled keep: https://x.com/OWW/status/2118117922350457059 
- dropped but labelled keep: https://x.com/AmericaGetBig/status/2118109734532243932 
- dropped but labelled keep: https://x.com/thesimaximalist/status/2118101838021132767 
- dropped but labelled keep: https://x.com/OWW/status/2118098193065849162 
- dropped but labelled keep: https://x.com/asteris_ai/status/2118090911632732510 
- dropped but labelled keep: https://x.com/asteris_ai/status/2118085888232321362 
- dropped but labelled keep: https://x.com/BriceTian/status/2118074574189306095 
- dropped but labelled keep: https://x.com/SanemBuilds/status/2118073762272924138 
- dropped but labelled keep: https://x.com/OWW/status/2118064557272735791 
- dropped but labelled keep: https://x.com/vincieye/status/2118064550100480448 
- dropped but labelled keep: https://x.com/SystemsAndCtrl/status/2118030962328015203 
- dropped but labelled keep: https://x.com/bobbyships/status/2118020579370373388 
- dropped but labelled keep: https://x.com/OWW/status/2117995559264845838 
- dropped but labelled keep: https://x.com/OWW/status/2117984443826651150 
- dropped but labelled keep: https://x.com/hrishikesh_ai/status/2117963733091913858 

Labels were written by Claude for this eval and are pending human review.
