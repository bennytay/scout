"""Writes. Every function is idempotent: re-running ingestion never duplicates rows."""
import json
import re
import unicodedata

import numpy as np
from psycopg.types.json import Jsonb

from .. import db
from ..models import TOPICS, Enrichment, Item

ORG_ALIASES = {  # small hand-curated map; extend as needed
    "deepmind": "Google DeepMind", "google deepmind": "Google DeepMind", "nvidia research": "NVIDIA",
    "nvidia corporation": "NVIDIA", "nvidia-omniverse": "NVIDIA", "nvidia omniverse": "NVIDIA", "meta ai": "Meta", "fair": "Meta", "facebook ai research": "Meta",
    "meta fair": "Meta", "pi": "Physical Intelligence", "physical-intelligence": "Physical Intelligence",
    "tri": "Toyota Research Institute", "mit": "MIT", "massachusetts institute of technology": "MIT",
    "cmu": "Carnegie Mellon University", "uc berkeley": "UC Berkeley", "berkeley": "UC Berkeley",
    "university of california, berkeley": "UC Berkeley", "eth zurich": "ETH Zurich", "eth zürich": "ETH Zurich",
    "huggingface": "Hugging Face", "auki": "Auki Labs", "auki network": "Auki Labs",
}


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", s)).strip().lower()


async def merge_sighting(item_id: int, item: Item) -> None:
    """An already-known item was seen again (another source, or a Discord share)."""
    await db.execute(
        "insert into item_sources (item_id, source, source_ref) values (%s, %s, %s) on conflict do nothing",
        item_id, item.source, item.source_ref or "",
    )
    await db.execute(
        """update items set metrics = metrics || %s,
                            submitted_by = coalesce(submitted_by, %s)
           where id = %s""",
        Jsonb(item.metrics), item.submitted_by, item_id,
    )


async def upsert_author(name: str, x_handle: str | None = None) -> int:
    row = await db.fetchrow(
        """insert into authors (name, normalized_name) values (%s, %s)
           on conflict (normalized_name) do update set name = authors.name returning id""",
        name.strip(), normalize(name),
    )
    if x_handle:
        await db.execute(
            """update authors set x_handle = %s where id = %s and x_handle is null
               and not exists (select 1 from authors where lower(x_handle) = lower(%s))""",
            x_handle, row["id"], x_handle,
        )
    return row["id"]


async def upsert_org(name: str) -> int:
    canon = ORG_ALIASES.get(normalize(name), name.strip())
    row = await db.fetchrow(
        """insert into orgs (name, normalized_name, aliases) values (%s, %s, %s)
           on conflict (normalized_name) do update
             set aliases = (select array(select distinct unnest(orgs.aliases || excluded.aliases)))
           returning id""",
        canon, normalize(canon), [normalize(name)] if normalize(name) != normalize(canon) else [],
    )
    return row["id"]


async def insert_item(item: Item, canonical_url: str, e: Enrichment | None, embedding: np.ndarray | None,
                      cost: float, model: str, outlinks: list[str]) -> int:
    row = await db.fetchrow(
        """insert into items (canonical_url, type, title, summary, full_text, published_at, source, source_ref,
                              submitted_by, arxiv_id, doi, metrics, entities, auki_relevance,
                              auki_relevance_reason, enrich_status, enrich_model, cost_usd, embedding, outlinks)
           values (%s, %s::item_type, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           on conflict (canonical_url) do update set metrics = items.metrics || excluded.metrics
           returning id""",
        canonical_url, item.type.value, item.title[:500], e.summary if e else item.summary, item.full_text,
        item.published_at, item.source, item.source_ref, item.submitted_by, item.arxiv_id, item.doi,
        Jsonb(item.metrics), Jsonb(e.entities.model_dump() if e else {}),
        e.auki_relevance if e else None, e.auki_relevance_reason if e else None,
        "done" if e else "failed", model, round(cost, 6), embedding, outlinks,
    )
    item_id = row["id"]
    await db.execute(
        "insert into item_sources (item_id, source, source_ref) values (%s, %s, %s) on conflict do nothing",
        item_id, item.source, item.source_ref or "",
    )
    if e:
        x_handle = item.author_handles.get("x")
        for pos, name in enumerate(dict.fromkeys(e.authors[:30])):
            if name.strip():
                aid = await upsert_author(name, x_handle if pos == 0 else None)
                await db.execute("insert into item_authors values (%s, %s, %s) on conflict do nothing",
                                 item_id, aid, pos)
        for name in dict.fromkeys(e.orgs + item.orgs):
            if name.strip():
                oid = await upsert_org(name)
                await db.execute("insert into item_orgs values (%s, %s) on conflict do nothing", item_id, oid)
        for rank, t in enumerate(x for x in e.topics if x in TOPICS):
            await db.execute("insert into item_topics values (%s, %s, %s) on conflict do nothing",
                             item_id, t, round(1.0 - 0.2 * rank, 2))
    return item_id


def dumps(x) -> str:
    return json.dumps(x, default=str)
