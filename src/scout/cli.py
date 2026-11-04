"""`scout <command>`: one entry point for cron, local dev, and the bot/MCP processes."""
import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

from . import db, log


def _print(x) -> None:
    print(json.dumps(x, indent=2, default=str, ensure_ascii=False))


async def _ingest(a):
    from .connectors import REGISTRY
    from .pipeline.run import run_connector

    names = a.source or list(REGISTRY)
    since = datetime.now(UTC) - timedelta(days=a.days) if a.days else None
    failed = 0
    for n in names:
        stats = await run_connector(n, since=since, only_value=a.value)
        failed += bool(stats.errors)
        print(f"{n:12} fetched={stats.fetched:4} new={stats.inserted:4} dup={stats.duplicates:4} "
              f"failed={stats.failed:3} cost=${stats.cost:.4f} errors={len(stats.errors)}", file=sys.stderr)
    return failed


async def _main(a) -> int:
    from . import health, search

    try:
        if a.cmd == "migrate":
            print(await db.migrate() or "up to date")
        elif a.cmd == "ingest":
            await _ingest(a)  # source failures are reported by `scout health`, not the exit code
        elif a.cmd == "add":
            from .pipeline.run import ingest_url

            r = await ingest_url(a.url, submitted_by=a.by)
            _print({"status": r.status, "item": await search.get_item(r.item_id) if r.item_id else None, "error": r.error})
        elif a.cmd == "search":
            _print(await search.search(query=a.query, author=a.author, org=a.org, topic=a.topic, type=a.type,
                                       since=a.since, limit=a.limit))
        elif a.cmd == "ask":
            r = await search.ask(a.question)
            print(r["answer"] + "\n")
            for x in r["sources"]:
                print(f"[{x['n']}] {x['title']} {x['url']}")
        elif a.cmd == "trending":
            _print(await search.trending(a.topic, a.days))
        elif a.cmd == "brief":
            from .bot.format import render_brief
            from .brief import make_brief
            from .config import settings

            since = datetime.now(UTC) - timedelta(hours=a.hours) if a.hours else None
            b = await make_brief(since=since, save=not a.dry_run)
            if not b:
                print("nothing in the window")
            else:
                msgs = render_brief(b, x_monitored=bool(settings().x_bearer_token))
                print("\n\n----- (next message) -----\n\n".join(msgs))
                print(f"\n[{b['n_candidates']} candidates · {b['model']} · ${b['cost_usd']}]", file=sys.stderr)
                if a.post:
                    await _post_to_feed(msgs)
        elif a.cmd == "health":
            problems = await health.problems()
            print("\n".join(problems) or "healthy")
            if problems and a.notify:
                await health.notify(problems)
            return 1 if problems else 0
        elif a.cmd == "enrich-retry":
            await _retry_failed()
        elif a.cmd == "reembed":
            print(f"re-embedded {await _reembed(a.all)} items")
    finally:
        await db.close()
    return 0


async def _post_to_feed(msgs: list[str]) -> None:
    """Post via Discord's REST API with the bot token (no gateway connection needed)."""
    import httpx

    from .config import settings

    cfg = settings()
    async with httpx.AsyncClient(timeout=20) as http:
        for m in msgs:
            r = await http.post(f"https://discord.com/api/v10/channels/{cfg.discord_feed_channel_id}/messages",
                                headers={"Authorization": f"Bot {cfg.discord_token}"},
                                json={"content": m, "flags": 4})  # 4 = suppress link previews
            r.raise_for_status()


async def _reembed(everything: bool) -> int:
    """(Re)build embeddings, e.g. after switching EMBEDDING_PROVIDER. Same text recipe as the pipeline."""
    import numpy as np

    from .providers.embeddings import get_embedder

    emb = get_embedder()
    where = "" if everything else "where embedding is null"
    rows = await db.fetch(f"select id, title, summary, full_text from items {where} order by id")
    for i in range(0, len(rows), 64):
        batch = rows[i:i + 64]
        vecs, _ = await emb.embed([f"{r['title']}\n{(r['summary'] or r['full_text'] or '')[:2000]}" for r in batch])
        for r, v in zip(batch, vecs, strict=True):
            await db.execute("update items set embedding = %s where id = %s", np.array(v, dtype=np.float32), r["id"])
    return len(rows)


async def _retry_failed():
    """Re-enrich items whose LLM call failed earlier (e.g. provider outage)."""
    from .pipeline.store import reenrich

    rows = await db.fetch("select id from items where enrich_status = 'failed' order by id limit 500")
    cost = 0.0
    for r in rows:
        cost += await reenrich(r["id"])
    print(f"re-enriched {len(rows)} items, ${cost:.4f}")


def main() -> None:
    p = argparse.ArgumentParser(prog="scout", description="Robotics research radar for Auki Labs")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply SQL migrations")
    i = sub.add_parser("ingest", help="run connectors")
    i.add_argument("--source", action="append", help="connector name (repeatable); default all")
    i.add_argument("--value", help="only this tracked source value")
    i.add_argument("--days", type=int, help="look-back window (default LOOKBACK_DAYS)")
    ad = sub.add_parser("add", help="ingest one URL now")
    ad.add_argument("url")
    ad.add_argument("--by", default="cli")
    se = sub.add_parser("search")
    se.add_argument("query", nargs="?")
    for f in ("author", "org", "topic", "type", "since"):
        se.add_argument(f"--{f}")
    se.add_argument("--limit", type=int, default=10)
    ak = sub.add_parser("ask")
    ak.add_argument("question")
    tr = sub.add_parser("trending")
    tr.add_argument("--topic")
    tr.add_argument("--days", type=int, default=7)
    br = sub.add_parser("brief", help="write the news brief (top 7-10 stories) for the window")
    br.add_argument("--hours", type=int, help="window length (default: since the last brief)")
    br.add_argument("--dry-run", action="store_true", help="don't save it")
    br.add_argument("--post", action="store_true", help="also post it to the Discord feed channel")
    h = sub.add_parser("health")
    h.add_argument("--notify", action="store_true", help="post problems to DISCORD_ALERTS_WEBHOOK_URL")
    sub.add_parser("enrich-retry", help="re-run enrichment for items where it failed")
    re_ = sub.add_parser("reembed", help="rebuild embeddings (items without one, or --all)")
    re_.add_argument("--all", action="store_true")
    m = sub.add_parser("mcp", help="run the MCP server")
    m.add_argument("--http", action="store_true", help="streamable HTTP with bearer auth (default stdio)")
    sub.add_parser("bot", help="run the Discord bot: monitors every source and posts the feed")
    sub.add_parser("web", help="run the web UI: search and maintain the database (http://127.0.0.1:8000)")
    a = p.parse_args()

    log.setup()
    if a.cmd == "mcp":
        from . import mcp_server

        mcp_server.run_http() if a.http else mcp_server.run_stdio()
        return
    if a.cmd == "web":
        from .web.app import run as run_web

        asyncio.run(db.migrate())
        run_web()
        return
    if a.cmd == "bot":
        from .bot.main import run

        asyncio.run(db.migrate())
        run()
        return
    sys.exit(asyncio.run(_main(a)))


if __name__ == "__main__":
    main()
