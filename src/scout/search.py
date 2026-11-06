"""Read side: hybrid search, item detail, related items, author profiles, what's stored, /ask.

Shared by the MCP server and the Discord bot, so both always give the same answers.
"""
import re
from datetime import UTC, datetime, timedelta

import numpy as np
from pydantic import BaseModel, Field

from . import db
from .log import log
from .models import TOPICS
from .providers.embeddings import get_embedder
from .providers.llm import get_llm

TOPIC_SYNONYMS = {
    "slam": "slam-spatial-mapping", "mapping": "slam-spatial-mapping", "spatial": "slam-spatial-mapping",
    "localization": "slam-spatial-mapping", "vla": "vla-foundation-models", "foundation": "vla-foundation-models",
    "humanoid": "humanoids", "dataset": "datasets-benchmarks", "benchmark": "datasets-benchmarks",
    "multi-robot": "multi-agent", "fleet": "multi-agent", "sim": "sim2real", "simulation": "sim2real",
    "grasping": "manipulation", "legged": "locomotion",
}
ITEM_COLUMNS = """
  i.id, i.title, i.canonical_url as url, i.type::text as type, i.summary, i.published_at, i.source,
  i.importance, i.auki_relevance, i.auki_relevance_reason, i.metrics, i.submitted_by, i.media,
  coalesce((select array_agg(a.name order by ia.position) from item_authors ia
            join authors a on a.id = ia.author_id where ia.item_id = i.id), '{}') as authors,
  coalesce((select array_agg(o.name order by o.name) from item_orgs io
            join orgs o on o.id = io.org_id where io.item_id = i.id), '{}') as orgs,
  coalesce((select array_agg(t.topic_slug order by t.confidence desc) from item_topics t
            where t.item_id = i.id), '{}') as topics,
  coalesce((select array_agg(distinct s.source) from item_sources s where s.item_id = i.id), '{}') as seen_in
"""


def resolve_topic(topic: str | None) -> str | None:
    if not topic:
        return None
    t = topic.strip().lower().replace(" ", "-").replace("/", "-")
    if t in TOPICS:
        return t
    for k, v in TOPIC_SYNONYMS.items():
        if k in t:
            return v
    return next((s for s in TOPICS if t in s), None)


def parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    if m := re.fullmatch(r"(\d+)\s*([dwmy])", since.strip().lower()):
        days = int(m.group(1)) * {"d": 1, "w": 7, "m": 30, "y": 365}[m.group(2)]
        return datetime.now(UTC) - timedelta(days=days)
    dt = datetime.fromisoformat(since)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _clean(row: dict) -> dict:
    out = {k: v for k, v in row.items() if v not in (None, [], {}, "")}
    if isinstance(out.get("published_at"), datetime):
        out["published_at"] = out["published_at"].date().isoformat()
    for k in ("importance", "auki_relevance"):
        if k in out:
            out[k] = round(float(out[k]), 2)
    if "score" in out:
        out["score"] = round(float(out["score"]), 4)
    return out


async def hydrate(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    rows = await db.fetch(f"select {ITEM_COLUMNS} from items i where i.id = any(%s)", ids)
    by_id = {r["id"]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


async def _embed_query(q: str | None):
    if not q:
        return None
    try:
        [v], _ = await get_embedder().embed([q], query=True)
        return np.array(v, dtype=np.float32)
    except Exception as e:  # degrade to lexical-only search
        log.warning("search.embed_failed", error=repr(e)[:200])
        return None


async def search(query: str | None = None, author: str | None = None, org: str | None = None,
                 topic: str | None = None, type: str | None = None, source: str | None = None,
                 since: str | None = None, until: str | None = None, min_relevance: float | None = None,
                 limit: int = 10) -> list[dict]:
    from .pipeline.store import normalize

    topic_slug = resolve_topic(topic)
    author = normalize(author) if author and not author.startswith("@") else author
    org = normalize(org) if org else org
    rows = await db.fetch(
        """select * from search_items(%s::text, %s::vector, %s::text, %s::text, %s::text, %s::item_type,
                                     %s::text, %s::timestamptz, %s::timestamptz, %s::real, %s::int)""",
        query or None, await _embed_query(query), author, org, topic_slug, type, source,
        parse_since(since), parse_since(until), min_relevance, min(max(limit, 1), 50),
    )
    items = await hydrate([r["item_id"] for r in rows])
    meta = {r["item_id"]: r for r in rows}
    return [_clean({**i, "score": meta[i["id"]]["score"], "matched": meta[i["id"]]["matched"]}) for i in items]


async def get_item(item_id: int) -> dict | None:
    [item] = await hydrate([item_id]) or [None]
    if not item:
        return None
    extra = await db.fetchrow(
        "select full_text is not null as has_full_text, entities, cost_usd, ingested_at from items where id = %s",
        item_id)
    item.update(extra)
    item["related"] = await find_related(item_id, limit=5)
    return _clean(item)


async def find_related(item_id: int, limit: int = 8) -> list[dict]:
    """Explicit links first (repo implements paper, post discusses paper), then nearest neighbours."""
    links = await db.fetch(
        """select dst_item_id as id, relation from item_links where src_item_id = %s
           union all
           select src_item_id, case relation when 'implements' then 'implemented_by'
                                             when 'discusses' then 'discussed_by' else relation end
           from item_links where dst_item_id = %s""", item_id, item_id)
    rel = {r["id"]: r["relation"] for r in links}
    near = await db.fetch(
        """select n.id, 1 - (n.embedding <=> me.embedding) as similarity
           from items me, items n
           where me.id = %s and n.id <> me.id and n.embedding is not null and me.embedding is not null
           order by n.embedding <=> me.embedding limit %s""", item_id, limit)
    sims = {r["id"]: round(float(r["similarity"]), 3) for r in near}
    ids = list(dict.fromkeys(list(rel) + list(sims)))[:limit]
    out = []
    for i in await hydrate(ids):
        i = {k: i[k] for k in ("id", "title", "url", "type", "published_at", "topics")}
        i["relation"] = rel.get(i["id"], "similar")
        if i["id"] in sims:
            i["similarity"] = sims[i["id"]]
        out.append(_clean(i))
    return out


async def author_profile(name: str) -> dict | None:
    a = await db.fetchrow(
        """select a.*, word_similarity(%s, a.name) as sim,
                  (select count(*) from item_authors ia where ia.author_id = a.id) as n_items
           from authors a
           where %s <%% a.name or lower(%s) = any(a.aliases) or lower(ltrim(%s, '@')) = lower(a.x_handle)
           order by sim desc, n_items desc limit 1""", name, name, name, name)
    if not a:
        return None
    items = await db.fetch(
        """select i.id from item_authors ia join items i on i.id = ia.item_id
           where ia.author_id = %s order by i.published_at desc nulls last limit 15""", a["id"])
    topics = await db.fetch(
        """select t.topic_slug as topic, count(*) as n from item_authors ia
           join item_topics t on t.item_id = ia.item_id where ia.author_id = %s
           group by 1 order by 2 desc""", a["id"])
    coauthors = await db.fetch(
        """select b.name, count(*) as n from item_authors ia
           join item_authors ib on ib.item_id = ia.item_id and ib.author_id <> ia.author_id
           join authors b on b.id = ib.author_id
           where ia.author_id = %s group by 1 order by 2 desc limit 10""", a["id"])
    orgs = await db.fetch(
        """select o.name, count(*) as n from item_authors ia join item_orgs io on io.item_id = ia.item_id
           join orgs o on o.id = io.org_id where ia.author_id = %s group by 1 order by 2 desc limit 5""", a["id"])
    return _clean({
        "name": a["name"], "x_handle": a["x_handle"], "github_handle": a["github_handle"],
        "items_in_db": a["n_items"], "topics": topics, "frequent_coauthors": coauthors, "orgs": orgs,
        "avatar": (await db.fetchrow(
            """select i.media->>'avatar' as a from item_authors ia join items i on i.id = ia.item_id
               where ia.author_id = %s and i.media ? 'avatar' limit 1""", a["id"]) or {}).get("a"),
        "recent_items": [_clean({k: i[k] for k in ("id", "title", "url", "type", "published_at")})
                         for i in await hydrate([r["id"] for r in items])],
    })


# ---------- lookups for Discord slash commands (no LLM) ----------

async def linked(ids: list[int]) -> dict[int, list[dict]]:
    """For each item, what it's explicitly linked to (a post -> its paper/repo/model, a paper -> its code)."""
    if not ids:
        return {}
    rows = await db.fetch(
        """select l.src_item_id as a, l.dst_item_id as b from item_links l
           where l.src_item_id = any(%s) or l.dst_item_id = any(%s)""", ids, ids)
    other = {r["b"] for r in rows} | {r["a"] for r in rows}
    info = {r["id"]: r for r in await db.fetch(
        "select id, type::text as type, title, canonical_url as url from items where id = any(%s)", list(other))}
    out: dict[int, list[dict]] = {i: [] for i in ids}
    for r in rows:
        for me, them in ((r["a"], r["b"]), (r["b"], r["a"])):
            if me in out and them in info and info[them] not in out[me]:
                out[me].append(dict(info[them]))
    return out


async def authors_like(prefix: str, limit: int = 25) -> list[dict]:
    """Autocomplete: authors by name or X handle (fuzzy), most items first."""
    p = prefix.strip().lstrip("@")
    return await db.fetch(
        """select a.name, a.x_handle, count(ia.item_id) as n
           from authors a join item_authors ia on ia.author_id = a.id
           where %s = '' or a.name ilike %s or a.x_handle ilike %s or %s <%% a.name
           group by a.id
           order by (%s <> '' and (a.name ilike %s or a.name ilike %s or coalesce(a.x_handle, '') ilike %s)) desc, n desc, a.name
           limit %s""",
        p, f"%{p}%", f"{p}%", p, p, f"{p}%", f"% {p}%", f"{p}%", limit)


async def recent(days: int = 3, limit: int = 10) -> dict:
    """What's stored: counts for the window, then the most important X posts (with what they link to)."""
    counts = await db.fetch(
        """select type::text as type, count(*) as n from items
           where ingested_at >= now() - make_interval(days => %s) group by 1 order by 2 desc""", days)
    total = await db.fetchrow("select count(*) as n from items")
    top = await db.fetch(
        """select id from items where ingested_at >= now() - make_interval(days => %s)
           and (type = 'post' or submitted_by is not null)
           order by coalesce(importance, auki_relevance) desc nulls last, ingested_at desc limit %s""", days, limit)
    return {"days": days, "total": total["n"], "by_type": {r["type"]: r["n"] for r in counts},
            "top": [_clean(i) for i in await hydrate([r["id"] for r in top])]}


# ---------- /ask: natural-language question → filters → search → cited answer ----------

class QueryPlan(BaseModel):
    query: str = Field(description="Keywords/phrase to search for, without the filter parts. Empty if none.")
    author: str | None = Field(None, description="Person name if the question is about a specific author.")
    org: str | None = Field(None, description="Organisation if the question is about a lab/company.")
    topic: str | None = Field(None, description=f"One of: {', '.join(TOPICS)}; null if not specific.")
    type: str | None = Field(None, description="paper|repo|post|article|model|dataset|video, or null.")
    since_days: int | None = Field(None, description="Look-back window in days if the question implies one.")


PLAN_SYSTEM = "Convert a question about robotics research into search filters. Only set filters the question clearly implies."
ANSWER_SYSTEM = """You answer questions about robotics news for the Auki Labs team using ONLY the numbered sources provided.
Cite sources inline as [1], [2]. If the sources don't answer the question, say so plainly.
Be concise: at most 8 sentences or a short bullet list. Answer the question as asked; only add an Auki angle
when an item is clearly relevant to Auki's spatial-computing work."""


async def ask(question: str, limit: int = 8) -> dict:
    llm = get_llm()
    cost = 0.0
    try:
        plan, c = await llm.structured(PLAN_SYSTEM, question, QueryPlan)
        cost += c
    except Exception:
        plan = QueryPlan(query=question)
    if plan.type not in (None, "paper", "repo", "post", "article", "model", "dataset", "video"):
        plan.type = None
    kw = {"query": plan.query or None, "author": plan.author, "org": plan.org, "topic": plan.topic, "type": plan.type,
              "since": f"{plan.since_days}d" if plan.since_days else None, "limit": limit}
    results = await search(**kw)
    if len(results) < 3 and any([plan.author, plan.org, plan.topic, plan.type, plan.since_days]):
        # filters too strict (e.g. an org the model didn't extract): top up with a plain search
        seen = {r["id"] for r in results}
        results += [r for r in await search(query=question, limit=limit) if r["id"] not in seen]
        results = results[:limit]
    if not results:
        return {"answer": "I couldn't find anything in the database about that yet.", "sources": [], "plan": kw}
    context = "\n\n".join(
        f"[{n}] {r['title']} ({r['type']}, {r.get('published_at', 'n.d.')}; {', '.join(r.get('authors', [])[:4])})\n"
        f"URL: {r['url']}\nSummary: {r.get('summary', '')}\nImportance (0-1): {r.get('importance', '?')}\n"
        f"Auki angle: {r.get('auki_relevance_reason', '')}"
        for n, r in enumerate(results, 1))
    answer, c = await llm.text(ANSWER_SYSTEM, f"Question: {question}\n\nSources:\n{context}", max_tokens=1200)
    cost += c
    sources = [{"n": n, "id": r["id"], "title": r["title"], "url": r["url"], "type": r["type"],
                "published_at": r.get("published_at")} for n, r in enumerate(results, 1)]
    return {"answer": answer, "sources": sources, "plan": kw, "cost_usd": round(cost, 5)}
