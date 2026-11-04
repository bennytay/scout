"""Offline eval: tagging accuracy + search quality on a hand-labelled set.

    uv run python evals/run.py            # uses the providers in .env (LLM_PROVIDER / EMBEDDING_PROVIDER)
    LLM_PROVIDER=fake EMBEDDING_PROVIDER=fake uv run python evals/run.py   # keyword-heuristic baseline

Loads evals/items.jsonl into a throwaway database (EVAL_DATABASE_URL), runs the real pipeline, then scores:
- topics: primary-topic accuracy, any-overlap accuracy, micro precision/recall/F1 over topic sets
- relevance: band accuracy (high ≥0.7 / mid 0.4–0.7 / low <0.4)
- search: precision@5, recall@5, MRR, hit@1 over evals/queries.jsonl; exact-author filter precision
Writes evals/results.md (+ results.json).
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg

HERE = Path(__file__).parent
EVAL_DSN = os.environ.get("EVAL_DATABASE_URL", "postgresql://scout:scout@localhost:54329/scout_eval")
os.environ["DATABASE_URL"] = EVAL_DSN
sys.path.insert(0, str(HERE.parent / "src"))

from scout import db, log, search
from scout.config import settings
from scout.models import Item, ItemType
from scout.pipeline.run import Pipeline


def band(x: float | None) -> str:
    return "high" if (x or 0) >= 0.7 else "mid" if (x or 0) >= 0.4 else "low"


def load(name: str) -> list[dict]:
    return [json.loads(l) for l in (HERE / name).read_text().splitlines() if l.strip()]


async def fresh_db():
    admin = EVAL_DSN.rsplit("/", 1)[0] + "/postgres"
    name = EVAL_DSN.rsplit("/", 1)[1]
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f"drop database if exists {name} with (force)")
        c.execute(f"create database {name}")
    await db.migrate(EVAL_DSN)


async def main():
    log.setup("WARNING")
    await fresh_db()
    items, queries, aqueries = load("items.jsonl"), load("queries.jsonl"), load("author_queries.jsonl")
    pipe = Pipeline(concurrency=8)
    results = await asyncio.gather(*(pipe.process(Item(
        url=f"https://arxiv.org/abs/{x['arxiv_id']}", type=ItemType.paper, title=x["title"], summary=x["summary"],
        authors=x["authors"], arxiv_id=x["arxiv_id"], source="eval",
        published_at=datetime.fromisoformat(x["published_at"]))) for x in items))
    cost = sum(r.cost for r in results)
    failed = [r for r in results if r.status == "failed"]

    rows = await db.fetch(
        """select i.arxiv_id, i.auki_relevance, i.enrich_status,
                  coalesce(array_agg(t.topic_slug order by t.confidence desc) filter (where t.topic_slug is not null), '{}') as topics
           from items i left join item_topics t on t.item_id = i.id group by i.id""")
    pred = {r["arxiv_id"]: r for r in rows}

    tp = fp = fn = primary = overlap = band_ok = 0
    confusion: dict[str, dict[str, int]] = {b: {"high": 0, "mid": 0, "low": 0} for b in ("high", "mid", "low")}
    misses = []
    for x in items:
        p = pred.get(x["arxiv_id"])
        ptopics = set(p["topics"]) if p else set()
        exp = set(x["expected_topics"])
        tp += len(ptopics & exp)
        fp += len(ptopics - exp)
        fn += len(exp - ptopics)
        primary += bool(p and p["topics"] and p["topics"][0] in exp)
        overlap += bool(ptopics & exp)
        b = band(p["auki_relevance"] if p else None)
        confusion[x["expected_relevance_band"]][b] += 1
        band_ok += b == x["expected_relevance_band"]
        if b != x["expected_relevance_band"] or not (ptopics & exp):
            misses.append({"title": x["title"][:80], "expected": [sorted(exp), x["expected_relevance_band"]],
                           "got": [p["topics"] if p else [], round(p["auki_relevance"] or 0, 2) if p else None]})
    n = len(items)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0

    qres = []
    for q in queries:
        rel = set(q["relevant_arxiv_ids"])
        got = [r["url"].rsplit("/", 1)[-1] for r in await search.search(q["query"], limit=10)]
        ranks = [i for i, a in enumerate(got, 1) if a in rel]
        qres.append({"query": q["query"], "p@5": len([a for a in got[:5] if a in rel]) / min(5, len(rel)),
                     "r@5": len([a for a in got[:5] if a in rel]) / len(rel),
                     "rr": 1 / ranks[0] if ranks else 0.0, "hit@1": bool(got and got[0] in rel)})
    ares = []
    for q in aqueries:
        got = [r["url"].rsplit("/", 1)[-1] for r in await search.search(author=q["author"], limit=10)]
        rel = set(q["relevant_arxiv_ids"])
        ares.append({"author": q["author"], "precision": len(set(got) & rel) / len(got) if got else 0,
                     "recall": len(set(got) & rel) / len(rel)})

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    s = settings()
    summary = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "llm": f"{s.llm_provider}:{s.llm_model}" if s.llm_provider != "fake" else "fake (keyword heuristic baseline)",
        "embeddings": f"{s.embedding_provider}:{s.embedding_model}" if s.embedding_provider != "fake" else "fake (hashed BoW)",
        "n_items": n, "n_queries": len(queries), "failed": len(failed), "cost_usd": round(cost, 4),
        "topics": {"primary_acc": round(primary / n, 3), "any_overlap_acc": round(overlap / n, 3),
                   "micro_precision": round(precision, 3), "micro_recall": round(recall, 3),
                   "micro_f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0},
        "relevance": {"band_acc": round(band_ok / n, 3), "confusion_expected_vs_predicted": confusion},
        "search": {"p@5": round(mean([q["p@5"] for q in qres]), 3), "r@5": round(mean([q["r@5"] for q in qres]), 3),
                   "mrr": round(mean([q["rr"] for q in qres]), 3), "hit@1": round(mean([q["hit@1"] for q in qres]), 3)},
        "author_filter": {"precision": round(mean([a["precision"] for a in ares]), 3),
                          "recall": round(mean([a["recall"] for a in ares]), 3)},
    }
    (HERE / "results.json").write_text(json.dumps({"summary": summary, "queries": qres, "authors": ares,
                                                    "misses": misses}, indent=2))
    md = [f"# Eval results ({summary['date']})", "",
          f"- LLM: `{summary['llm']}` · embeddings: `{summary['embeddings']}`",
          (f"- {n} hand-labelled items, {len(queries)} search queries, {len(aqueries)} author queries · "
          f"enrichment cost ${summary['cost_usd']} · failures {len(failed)}"), "",
          "| Metric | Value |", "|---|---|"]
    for k, v in summary["topics"].items():
        md.append(f"| topics · {k} | {v:.0%} |")
    md.append(f"| relevance · band accuracy | {summary['relevance']['band_acc']:.0%} |")
    for k, v in summary["search"].items():
        md.append(f"| search · {k} | {v:.2f} |")
    md += [f"| author filter · precision | {summary['author_filter']['precision']:.0%} |",
           f"| author filter · recall | {summary['author_filter']['recall']:.0%} |", "",
           "Relevance confusion (rows = labelled, cols = predicted):", "",
           "| | high | mid | low |", "|---|---|---|---|"]
    for b, row in confusion.items():
        md.append(f"| **{b}** | {row['high']} | {row['mid']} | {row['low']} |")
    md += ["", "Per-query:", "", "| query | P@5 | RR |", "|---|---|---|"]
    md += [f"| {q['query']} | {q['p@5']:.2f} | {q['rr']:.2f} |" for q in qres]
    (HERE / "results.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:22]))
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
