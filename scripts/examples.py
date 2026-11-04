"""Run the README's example questions against the live database and write docs/examples.md.

    uv run python scripts/examples.py
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from scout import db, log, search  # noqa: E402
from scout.config import settings  # noqa: E402

ASK = [
    "What's new this week in visual localization or relocalization?",
    "Which recent papers build 3D scene graphs for robot memory?",
    "What are people releasing for humanoid whole-body control?",
    "Anything on multiple robots sharing a map?",
]
SEARCH = [
    dict(query="vision-language-action", since="7d", limit=5),
    dict(topic="slam-spatial-mapping", min_relevance=0.7, limit=5),
    dict(type="repo", topic="manipulation", limit=5),
]


async def main():
    log.setup("WARNING")
    s = settings()
    llm = "fake keyword heuristic, NOT an LLM: rerun with keys" if s.llm_provider == "fake" else f"{s.llm_provider}:{s.llm_model}"
    emb = "fake hashed bag-of-words" if s.embedding_provider == "fake" else f"{s.embedding_provider}:{s.embedding_model}"
    out = ["# Example questions and real answers", "",
           f"_Generated {datetime.now():%Y-%m-%d %H:%M} by `scripts/examples.py` against the live database "
           f"(LLM `{llm}`, embeddings `{emb}`). Re-run any time._", ""]
    for q in ASK:
        r = await search.ask(q)
        out += [f"## /ask {q}", "", r["answer"], ""]
        out += [f"{x['n']}. [{x['title']}]({x['url']})" for x in r["sources"][:6]] + [""]
    for kw in SEARCH:
        rows = await search.search(**kw)
        out += [f"## `search({', '.join(f'{k}={v!r}' for k, v in kw.items())})`", "",
                "| # | item | type | topics | Auki relevance |", "|---|---|---|---|---|"]
        out += [f"| {n} | [{r['title'][:90]}]({r['url']}) | {r['type']} | {', '.join(r.get('topics', []))} | "
                f"{r.get('auki_relevance', '–')} |" for n, r in enumerate(rows, 1)] + [""]
    tr = await search.trending(days=7, limit=5)
    out += ["## `trending(days=7)`", "", "| item | sources | score |", "|---|---|---|"]
    out += [f"| [{r['title'][:90]}]({r['url']}) | {', '.join(r.get('seen_in', []))} | {r['trend_score']} |" for r in tr]
    Path("docs/examples.md").write_text("\n".join(out) + "\n")
    print("\n".join(out[:30]))
    await db.close()


asyncio.run(main())
