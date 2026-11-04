"""Orchestration: fetch → normalise → canonicalise → dedupe → enrich → embed → upsert → link.

Per-source and per-item error isolation: one bad feed or one bad item never stops the run.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np
from psycopg.types.json import Jsonb
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .. import db
from ..config import settings
from ..connectors import REGISTRY, http_client
from ..connectors.resolve import resolve
from ..log import log
from ..models import Item
from ..providers.embeddings import get_embedder
from ..providers.llm import get_llm
from ..urls import arxiv_id_from, canonicalize, doi_from
from . import dedupe, store
from .enrich import enrich
from .link import extract_outlinks, link_item


@dataclass
class Result:
    item_id: int | None
    status: str  # inserted | duplicate | failed
    cost: float = 0.0
    error: str | None = None


@dataclass
class RunStats:
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    failed: int = 0
    cost: float = 0.0
    errors: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(self, concurrency: int = 5):
        self.llm = get_llm()
        self.embedder = get_embedder()
        self.sem = asyncio.Semaphore(concurrency)

    async def process(self, item: Item) -> Result:
        async with self.sem:
            try:
                return await self._process(item)
            except Exception as e:  # isolate per item
                log.warning("item.failed", url=item.url, error=repr(e)[:300])
                return Result(None, "failed", error=repr(e)[:300])

    async def _process(self, item: Item) -> Result:
        url = canonicalize(item.url)
        item.arxiv_id = item.arxiv_id or arxiv_id_from(url)
        item.doi = (item.doi or doi_from(url) or "").lower() or None

        if existing := await dedupe.exact_match(url, item.arxiv_id, item.doi):
            await store.merge_sighting(existing, item)
            return Result(existing, "duplicate")

        embed_text = f"{item.title}\n{(item.summary or item.full_text or '')[:2000]}"
        [vec], cost = await self.embedder.embed([embed_text])
        vec = np.array(vec, dtype=np.float32)
        if near := await dedupe.semantic_match(item.type.value, vec):
            await store.merge_sighting(near[0], item)
            log.info("item.semantic_dup", url=url, match=near[0], sim=round(near[1], 3))
            return Result(near[0], "duplicate", cost)

        enrichment, llm_cost = None, 0.0
        try:
            enrichment, llm_cost = await enrich(self.llm, item)
        except Exception as e:  # store the item anyway; enrich_status='failed' lets us retry later
            log.warning("enrich.failed", url=url, error=repr(e)[:300])
        cost += llm_cost

        outlinks = [u for u in extract_outlinks(item.outlinks, item.full_text) if u != url]
        item_id = await store.insert_item(item, url, enrichment, vec, cost, self.llm.model, outlinks)
        await link_item(item_id)
        log.info("item.inserted", id=item_id, url=url, cost=round(cost, 5),
                 relevance=enrichment.auki_relevance if enrichment else None)
        return Result(item_id, "inserted", cost)


@retry(retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
       stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30), reraise=True)
async def _fetch(connector, http, kind, value, since, state):
    if connector.stateful:
        return await connector.fetch(http, kind, value, since, state=state)
    return await connector.fetch(http, kind, value, since)


async def run_connector(name: str, since: datetime | None = None, only_value: str | None = None) -> RunStats:
    connector = REGISTRY[name]
    s = settings()
    stats = RunStats()
    missing = [k for k in connector.needs if not getattr(s, k)]
    if missing:
        log.info("connector.skipped", connector=name, missing=missing)
        return stats
    since = since or datetime.now(UTC) - timedelta(days=s.lookback_days)
    run = await db.fetchrow("insert into ingest_runs (connector) values (%s) returning id", name)
    sources = await db.fetch(
        "select id, kind, value, cursor from sources where enabled and kind = any(%s) order by id", list(connector.kinds)
    )
    if only_value:
        sources = [x for x in sources if x["value"] == only_value]
    pipe = Pipeline()
    async with http_client() as http:
        for src in sources:
            try:
                state = dict(src["cursor"] or {})
                items = (await _fetch(connector, http, src["kind"], src["value"], since, state))[: s.max_items_per_source]
                await db.execute(
                    """update sources set last_run_at = now(), last_success_at = now(), cursor = %s,
                       last_error = null, consecutive_failures = 0 where id = %s""", Jsonb(state), src["id"])
            except Exception as e:
                msg = f"{src['kind']}:{src['value']}: {e!r}"[:500]
                stats.errors.append(msg)
                log.error("source.failed", connector=name, source=src["value"], error=repr(e)[:300])
                await db.execute(
                    """update sources set last_run_at = now(), last_error = %s,
                       consecutive_failures = consecutive_failures + 1 where id = %s""", msg, src["id"])
                continue
            stats.fetched += len(items)
            for r in await asyncio.gather(*(pipe.process(i) for i in items)):
                stats.cost += r.cost
                if r.status == "inserted":
                    stats.inserted += 1
                elif r.status == "duplicate":
                    stats.duplicates += 1
                else:
                    stats.failed += 1
    status = "ok" if not stats.errors else ("failed" if len(stats.errors) == len(sources) else "partial")
    await db.execute(
        """update ingest_runs set finished_at = now(), status = %s, fetched = %s, inserted = %s,
           duplicates = %s, failed = %s, cost_usd = %s, error = %s where id = %s""",
        status, stats.fetched, stats.inserted, stats.duplicates, stats.failed, round(stats.cost, 6),
        "\n".join(stats.errors)[:2000] or None, run["id"],
    )
    log.info("connector.done", connector=name, status=status, **{k: v for k, v in stats.__dict__.items() if k != "errors"})
    return stats


async def ingest_url(url: str, submitted_by: str | None = None, follow_outlinks: bool = True) -> Result:
    """Priority path for Discord / MCP add_link. Also pulls in papers/repos the link points to."""
    pipe = Pipeline()
    async with http_client() as http:
        try:
            item = await resolve(http, url, source="discord" if submitted_by not in (None, "mcp") else "mcp")
        except Exception as e:
            log.warning("resolve.failed", url=url, error=repr(e)[:300])
            return Result(None, "failed", error=f"couldn't fetch {url}: {e.__class__.__name__}")
        item.submitted_by = submitted_by
        result = await pipe.process(item)
        if follow_outlinks and result.status == "inserted":
            me = canonicalize(item.url)
            targets = [u for u in extract_outlinks(item.outlinks, item.full_text) if u != me
                       and ("arxiv.org/abs/" in u or u.startswith("https://github.com/"))][:3]
            for u in targets:
                try:
                    sub = await pipe.process(await resolve(http, u, source=item.source))
                    if sub.item_id:
                        await link_item(sub.item_id)
                except Exception as e:
                    log.warning("outlink.failed", url=u, error=repr(e)[:200])
        return result


async def run_all(names: list[str] | None = None) -> dict[str, RunStats]:
    out = {}
    for name in names or list(REGISTRY):
        try:
            out[name] = await run_connector(name)
        except Exception as e:
            log.error("connector.crashed", connector=name, error=repr(e))
    return out
