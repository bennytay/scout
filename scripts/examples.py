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

ASK = [  # what someone would type after @Scout
    "What's new in humanoids this week, and who announced it?",
    "What did ETH's legged robotics people post about navigation, and is there code?",
    "Any new vision-language-action models I can actually download?",
    "Anything on robots sharing maps or relocalizing?",
]
SEARCH = [  # what /topic and /author run (no LLM)
    dict(topic="humanoids", since="3d", limit=6),
    dict(author="levine", limit=5),
    dict(query="world model", type="post", limit=5),
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
        out += [f"## @Scout {q}", "", r["answer"], ""]
        out += [f"{x['n']}. [{x['title']}]({x['url']})" for x in r["sources"][:6]] + [""]
    for kw in SEARCH:
        rows = await search.search(**kw)
        out += [f"## `search({', '.join(f'{k}={v!r}' for k, v in kw.items())})`", "",
                "| # | item | type | topics | Auki relevance |", "|---|---|---|---|---|"]
        out += [f"| {n} | [{r['title'][:90]}]({r['url']}) | {r['type']} | {', '.join(r.get('topics', []))} | "
                f"{r.get('auki_relevance', '–')} |" for n, r in enumerate(rows, 1)] + [""]
    r = await search.recent(days=3)
    out += ["## `/recent 3` (what's stored)", "", f"{r['total']} items stored; last 3 days: "
            + ", ".join(f"{n} {t}s" for t, n in r["by_type"].items()), ""]
    links = await search.linked([i["id"] for i in r["top"]])
    out += [f"- [{i['title'][:100]}]({i['url']})" + "".join(f" → [{lk['type']}]({lk['url']})" for lk in links[i["id"]])
            for i in r["top"]]
    Path("docs/examples.md").write_text("\n".join(out) + "\n")
    print("\n".join(out[:30]))
    await db.close()


asyncio.run(main())
