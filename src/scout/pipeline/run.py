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
from ..models import Item, ItemType
from ..providers.embeddings import get_embedder
from ..providers.llm import get_llm
from ..urls import arxiv_id_from, canonicalize, doi_from
from ..xsignal import DROP_SIGNALS
from . import dedupe, store
from .enrich import enrich
from .link import extract_outlinks, link_item

FOLLOW = ("https://arxiv.org/abs/", "https://github.com/", "https://huggingface.co/")
MAX_FOLLOW = 3


def is_scanned_x_post(item: Item) -> bool:
    """X posts found by the scan are judged; posts the team shared are always kept."""
    return item.source == "x" and item.type == ItemType.post and not item.submitted_by


def follow_targets(item: Item) -> list[str]:
    """The research an item points at: arXiv papers, GitHub repos, HF models/datasets, project pages."""
    me = canonicalize(item.url)
    out = [u for u in extract_outlinks(item.outlinks, item.full_text) if u != me
           and (u.startswith(FOLLOW) or ".github.io/" in u or u.endswith(".github.io"))]
    return out[:MAX_FOLLOW]


@dataclass
class Result:
    item_id: int | None
    status: str  # inserted | duplicate | dropped (judged low-signal) | failed
    cost: float = 0.0
    error: str | None = None


@dataclass
class RunStats:
    fetched: int = 0      # read from the source (for X: before the gate)
    inserted: int = 0
    dropped: int = 0      # X: removed by the gate or the judge
    duplicates: int = 0
    failed: int = 0
    cost: float = 0.0
    errors: list[str] = field(default_factory=list)
    new_ids: list[int] = field(default_factory=list)


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
        if enrichment and is_scanned_x_post(item) and enrichment.signal in DROP_SIGNALS:
            log.info("item.judged_out", url=url, signal=enrichment.signal)
            return Result(None, "dropped", cost)

        outlinks = [u for u in extract_outlinks(item.outlinks, item.full_text) if u != url]
        item_id = await store.insert_item(item, url, enrichment, vec, cost, self.llm.model, outlinks)
        await link_item(item_id)
        log.info("item.inserted", id=item_id, url=url, cost=round(cost, 5),
                 relevance=enrichment.auki_relevance if enrichment else None)
        return Result(item_id, "inserted", cost)


    async def follow(self, http: httpx.AsyncClient, item: Item) -> None:
        """Ingest what a kept post links to (paper, repo, model) and link them to it. Dedupes as usual."""
        for u in follow_targets(item):
            try:
                sub = await self.process(await resolve(http, u, source=item.source))
                if sub.item_id:
                    await link_item(sub.item_id)
            except Exception as e:
                log.warning("outlink.failed", url=u, error=repr(e)[:200])


@retry(retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
       stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30), reraise=True)
async def _fetch(connector, http, kind, value, since, state):
    if connector.stateful:
        return await connector.fetch(http, kind, value, since, state=state)
    return await connector.fetch(http, kind, value, since)


async def _fetch_one(connector, http, src, since, stats: RunStats) -> list[Item]:
    try:
        state = dict(src["cursor"] or {})
        items = (await _fetch(connector, http, src["kind"], src["value"], since, state))[: settings().max_items_per_source]
        await _source_ok(src["id"], state)
    except Exception as e:
        msg = f"{src['kind']}:{src['value']}: {e!r}"[:500]
        stats.errors.append(msg)
        log.error("source.failed", connector=connector.name, source=src["value"], error=repr(e)[:300])
        await _source_failed(src["id"], msg)
        return []
    stats.fetched += len(items)
    return items


async def _fetch_many(connector, http, sources, since, stats: RunStats) -> list[Item]:
    try:
        res = await connector.fetch_many(http, sources, since)
    except Exception as e:  # e.g. auth failure: the whole scan fails, the bot reports it
        stats.errors.append(f"{connector.name}: {e!r}"[:500])
        log.error("connector.fetch_failed", connector=connector.name, error=repr(e)[:300])
        return []
    for sid, state in res.states.items():
        await _source_ok(sid, state)
    for sid, msg in res.failed.items():
        await _source_failed(sid, msg)
    stats.errors += res.errors
    stats.fetched += res.seen
    stats.dropped += sum(res.dropped.values())
    return res.items


async def _source_ok(source_id: int, state: dict) -> None:
    await db.execute(
        """update sources set last_run_at = now(), last_success_at = now(), cursor = %s,
           last_error = null, consecutive_failures = 0 where id = %s""", Jsonb(state), source_id)


async def _source_failed(source_id: int, msg: str) -> None:
    await db.execute(
        """update sources set last_run_at = now(), last_error = %s,
           consecutive_failures = consecutive_failures + 1 where id = %s""", msg, source_id)


async def xsignal_record(items: list[Item], results: list[Result]) -> None:
    """Per-account hit rate: how many of an account's gated posts the judge kept (the 'learn' step)."""
    for it, r in zip(items, results, strict=True):
        h = (it.author_handles.get("x") or "").lower()
        if not h or r.status == "failed":
            continue
        kept = r.status in ("inserted", "duplicate")
        await db.execute(
            """insert into x_accounts (handle, judged, kept, last_kept_at) values (%s, 1, %s, case when %s then now() end)
               on conflict (handle) do update set judged = x_accounts.judged + 1,
                 kept = x_accounts.kept + excluded.kept,
                 last_kept_at = coalesce(excluded.last_kept_at, x_accounts.last_kept_at)""",
            h, int(kept), kept)


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
        if hasattr(connector, "fetch_many"):  # whole-scan connectors (X)
            batches = [await _fetch_many(connector, http, sources, since, stats)]
        else:
            batches = [await _fetch_one(connector, http, src, since, stats) for src in sources]
        for items in batches:
            results = await asyncio.gather(*(pipe.process(i) for i in items))
            for it, r in zip(items, results, strict=True):
                stats.cost += r.cost
                if r.status == "inserted":
                    stats.inserted += 1
                    stats.new_ids.append(r.item_id)
                    if is_scanned_x_post(it):
                        await pipe.follow(http, it)
                elif r.status == "duplicate":
                    stats.duplicates += 1
                elif r.status == "dropped":
                    stats.dropped += 1
                else:
                    stats.failed += 1
            if name == "x":
                await xsignal_record(items, results)
    status = "ok" if not stats.errors else ("failed" if not stats.fetched and stats.errors else "partial")
    await db.execute(
        """update ingest_runs set finished_at = now(), status = %s, fetched = %s, inserted = %s,
           duplicates = %s, failed = %s, dropped = %s, cost_usd = %s, error = %s where id = %s""",
        status, stats.fetched, stats.inserted, stats.duplicates, stats.failed, stats.dropped, round(stats.cost, 6),
        "\n".join(stats.errors)[:2000] or None, run["id"],
    )
    log.info("connector.done", connector=name, status=status, fetched=stats.fetched, inserted=stats.inserted,
             duplicates=stats.duplicates, dropped=stats.dropped, failed=stats.failed, cost=round(stats.cost, 5))
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
            await pipe.follow(http, item)
        return result


async def run_all(names: list[str] | None = None) -> dict[str, RunStats]:
    out = {}
    for name in names or list(REGISTRY):
        try:
            out[name] = await run_connector(name)
        except Exception as e:
            log.error("connector.crashed", connector=name, error=repr(e))
    return out
