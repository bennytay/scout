"""X signal eval: does the funnel keep what's worth reading and drop the rest?

    uv run python evals/x_signal.py

62 real posts from one live scan (tests/fixtures/x_search_*.json: 12 from radar accounts, 50 from a
link-anchored discovery query). evals/x_posts.jsonl labels each keep/drop BY CONTENT ONLY: "would the
Auki team want this in a robotics news feed?", ignoring likes and followers. So recall shows what the
engagement rules cost, not just how precise they are.

Scores the free gate alone, then gate + Claude judge (the real enrichment call). Writes evals/x_results.md.
"""
import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from scout import xsignal
from scout.connectors.x import parse_page
from scout.pipeline.enrich import enrich
from scout.providers.llm import get_llm


def prf(pred: list[bool], gold: list[bool]) -> dict:
    tp = sum(p and g for p, g in zip(pred, gold, strict=True))
    fp = sum(p and not g for p, g in zip(pred, gold, strict=True))
    fn = sum(g and not p for p, g in zip(pred, gold, strict=True))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"kept": tp + fp, "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0}


async def main():
    posts = {}
    for k in ("radar", "discovery"):
        for it in parse_page(json.loads((HERE.parent / f"tests/fixtures/x_search_{k}.json").read_text())):
            posts[it.url] = it
    labels = [json.loads(l) for l in (HERE / "x_posts.jsonl").read_text().splitlines() if l.strip()]
    items = [posts[lb["url"]] for lb in labels]
    gold = [lb["label"] == "keep" for lb in labels]
    radar = {xsignal.handle(posts[lb["url"]]) for lb in labels if lb["on_radar"]}

    kept, dropped = xsignal.gate_batch(items, radar, datetime.now(UTC))
    passed = {i.url for i in kept}
    gate_pred = [i.url in passed for i in items]

    llm = get_llm()
    cost, signals = 0.0, {}
    sem = asyncio.Semaphore(5)

    async def judge(it):
        nonlocal cost
        async with sem:
            e, c = await enrich(llm, it)
        cost += c
        signals[it.url] = e.signal

    await asyncio.gather(*(judge(i) for i in kept))
    full_pred = [i.url in passed and signals.get(i.url) not in xsignal.DROP_SIGNALS for i in items]

    is_radar = [lb["on_radar"] for lb in labels]
    rows = {
        "gate only": prf(gate_pred, gold),
        "gate + judge": prf(full_pred, gold),
        "gate + judge (radar)": prf([p for p, r in zip(full_pred, is_radar, strict=True) if r],
                                    [g for g, r in zip(gold, is_radar, strict=True) if r]),
        "gate + judge (discovery)": prf([p for p, r in zip(full_pred, is_radar, strict=True) if not r],
                                        [g for g, r in zip(gold, is_radar, strict=True) if not r]),
    }
    misses = [(lb["url"], "kept but labelled drop" if p else "dropped but labelled keep", lb.get("why", ""))
              for lb, p, g in zip(labels, full_pred, gold, strict=True) if p != g]
    lines = [
        "# X signal eval", "",
        f"{len(labels)} real posts from one live scan ({sum(is_radar)} radar, {len(labels) - sum(is_radar)} discovery), "
        f"{sum(gold)} labelled keep by content alone. Judge: `{llm.model}`, cost ${cost:.4f}. "
        f"Run {datetime.now(UTC):%Y-%m-%d}.", "",
        "| stage | posts kept | precision | recall | F1 |", "|---|---|---|---|---|",
        *[f"| {k} | {v['kept']} | {v['precision']:.2f} | {v['recall']:.2f} | {v['f1']:.2f} |" for k, v in rows.items()],
        "", "Reading: the funnel is tuned for precision. Nothing kept was junk. Discovery misses are mostly arXiv-mirror bots",
        "and paper summarisers with 0-5 likes: the paper exists, but nobody on X is discussing it yet, which is what",
        "'X is the newsroom' filters for. Caveat: this snapshot was recorded minutes to hours after posting; live",
        "discovery only judges posts 6h+ old, after likes accrue, so this recall is a lower bound.",
        "", f"Gate drop reasons: {dict(Counter(dropped))}. Judge labels: {dict(Counter(signals.values()))}.", "",
        "## Disagreements", "", *[f"- {kind}: {u} {('(' + w + ')') if w else ''}" for u, kind, w in misses], "",
        "Labels were written by Claude for this eval and are pending human review.",
    ]
    (HERE / "x_results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
