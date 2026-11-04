"""The news brief: a reasoning layer on top of the per-item pipeline.

Per-source updates are fragmented ("56 arXiv papers, 52 HF items…"). The brief answers the real question,
*what happened?*, in 7-10 stories:

1. Candidates: every on-topic X post in the window (X is where robotics news breaks), plus the most relevant
   and most-discussed papers/repos/models/articles. Each comes with its explicit links (post→paper, repo→paper)
   and nearest neighbours by meaning, so the editor can see what belongs together.
2. An editor model (Claude Opus by default) clusters candidates into stories, makes an X post the primary source
   whenever one exists, attaches the supporting paper/code/model/dataset, and ranks by importance.
3. The editor can only cite candidate ids. URLs are filled in from the database, so links can't be invented.
"""
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .log import log
from .providers.llm import get_llm

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
LABEL = {"paper": "paper", "repo": "code", "model": "model", "dataset": "dataset", "video": "video"}
SOURCE_NAME = {"arxiv": "arXiv", "github": "GitHub", "huggingface": "Hugging Face", "hackernews": "Hacker News",
               "alphaxiv": "alphaXiv", "rss": "RSS", "x": "X", "discord": "team links", "web": "web", "mcp": "MCP"}
MAX_X, MAX_OTHER = 60, 70
FILLER = {"for", "of", "the", "a", "an", "and", "to", "with", "via", "in", "on", "from", "by"}


class Story(BaseModel):
    headline: str = Field(description="<= 12 words, concrete, news-style. No emojis, no clickbait.")
    why: str = Field(description="One sentence, <= 22 words: what's new and why it matters.")
    primary_id: int = Field(description="Candidate id that IS the news. An X post whenever one covers the story.")
    supporting_ids: list[int] = Field(description="Up to 4 other candidate ids backing the story (paper, code, model...).")


class Brief(BaseModel):
    stories: list[Story] = Field(description="7-10 stories, most important first (fewer if the period was quiet).")


SYSTEM = """You are the editor of a robotics news brief for the Auki Labs team. From the numbered candidate items,
write the top 7-10 stories of this period.

Rules:
- A story is one development: a model or product release, a paper, a funding round, a demo, a dataset.
  Merge candidates that are about the same development into one story.
- X is the newsroom. If any X post covers the story, its id MUST be the primary_id. Otherwise use the most
  direct source (the paper, repo or model itself).
- supporting_ids: other candidates about the same story, most useful first (paper, code, model, dataset,
  discussion), at most 4. Never reuse an id in two stories.
- Rank by importance to a team building spatial computing and robots that share an understanding of space:
  real capability jumps and major releases first, then what people are talking about (likes, upvotes, stars,
  number of sources), then relevance to Auki. Skip minor incremental papers when there is real news.
- headline: <= 12 words, concrete, like a good news headline. why: one sentence <= 22 words.
- Only use facts in the candidate text. Only use candidate ids.

What Auki cares about:
{auki}"""


def _buzz(m: dict) -> str:
    parts = [("❤", m.get("x_likes")), ("▲", m.get("hf_upvotes")), ("★", m.get("gh_stars")),
             ("HN", m.get("hn_points")), ("ax", m.get("ax_votes")), ("♥", m.get("hf_likes"))]
    return " ".join(f"{k}{int(v)}" for k, v in parts if v)


def _first_sentence(text: str | None, n: int = 220) -> str:
    t = re.split(r"(?<=[.!?])\s+", " ".join((text or "").split()), maxsplit=1)[0]
    return t if len(t) <= n else t[: n - 1] + "…"


def short_name(title: str) -> str:
    """'Ray-SCR: Generalizing Scene Coordinate…' -> 'Ray-SCR'; 'huggingface/lerobot: …' -> 'lerobot'."""
    head = title.split(":")[0].strip()
    if "/" in head and " " not in head:
        return head.split("/")[-1]
    if len(head) <= 28 and head != title.strip():
        return head
    words = [w.rstrip(":;,.") for w in title.split()[:3]]
    while len(words) > 1 and words[-1].lower() in FILLER:
        words.pop()
    return " ".join(words)


def link_label(c: dict) -> str:
    if c["url"].startswith("https://x.com/"):
        return "𝕏 @" + c["url"].split("/")[3]
    if "news.ycombinator.com" in c["url"]:
        return "HN thread"
    if c["type"] in LABEL:
        return f"{LABEL[c['type']]}: {short_name(c['title'])}"
    return re.sub(r"^https?://(www\.)?", "", c["url"]).split("/")[0]


async def candidates(since: datetime, until: datetime) -> dict[int, dict]:
    cols = """i.id, i.type::text as type, i.title, i.summary, i.canonical_url as url, i.source,
              coalesce(i.auki_relevance, 0) as rel, i.metrics,
              (select count(distinct s.source) from item_sources s where s.item_id = i.id) as n_sources"""
    win = "i.ingested_at >= %s and i.ingested_at < %s and coalesce(i.auki_relevance, 0) >= 0.3"
    x_posts = await db.fetch(
        f"""select {cols} from items i where {win} and i.canonical_url like 'https://x.com/%%'
            order by coalesce((i.metrics->>'x_likes')::float, 0) desc limit {MAX_X}""", since, until)
    others = await db.fetch(
        f"""select {cols} from items i where {win} and i.canonical_url not like 'https://x.com/%%'
            order by 2 * coalesce(i.auki_relevance, 0)
                     + ln(1 + coalesce((i.metrics->>'hf_upvotes')::float, 0))
                     + ln(1 + coalesce((i.metrics->>'hn_points')::float, 0))
                     + 0.5 * ln(1 + coalesce((i.metrics->>'gh_stars')::float, 0))
                     + ln(1 + coalesce((i.metrics->>'ax_votes')::float, 0))
                     + (select count(distinct s.source) from item_sources s where s.item_id = i.id) desc
            limit {MAX_OTHER}""", since, until)
    pool = {r["id"]: dict(r) for r in x_posts + others}
    if not pool:
        return {}
    # explicit links, any age: a post this week can discuss a paper ingested last week
    links = await db.fetch(
        """select src_item_id as a, dst_item_id as b from item_links
           where src_item_id = any(%s) or dst_item_id = any(%s)""", list(pool), list(pool))
    extra = {x for lk in links for x in (lk["a"], lk["b"])} - set(pool)
    if extra:
        for r in await db.fetch(f"select {cols} from items i where i.id = any(%s)", list(extra)):
            pool[r["id"]] = dict(r)
    for c in pool.values():
        c["links"] = sorted({lk["b"] if lk["a"] == c["id"] else lk["a"] for lk in links if c["id"] in (lk["a"], lk["b"])})
    # nearest neighbours by meaning, within the pool: helps the editor merge a post with its paper/repo
    ids = list(pool)
    for r in await db.fetch(
        """select a.id, array(select b.id from items b where b.id = any(%s) and b.id <> a.id and b.embedding is not null
                              and 1 - (a.embedding <=> b.embedding) > 0.8
                              order by a.embedding <=> b.embedding limit 3) as near
           from items a where a.id = any(%s) and a.embedding is not null""", ids, ids):
        pool[r["id"]]["near"] = r["near"]
    return pool


def candidate_lines(pool: dict[int, dict]) -> str:
    def line(c):
        kind = "X POST" if c["url"].startswith("https://x.com/") else c["type"].upper()
        rel = [f"links→{c['links']}"] if c.get("links") else []
        rel += [f"similar→{c['near']}"] if c.get("near") else []
        return (f"[{c['id']}] {kind} · {SOURCE_NAME.get(c['source'], c['source'])} · rel {c['rel']:.2f}"
                f"{' · ' + _buzz(c['metrics']) if _buzz(c['metrics']) else ''}"
                f"{' · seen in ' + str(c['n_sources']) + ' sources' if c['n_sources'] > 1 else ''}\n"
                f"    {c['title'][:160]}: {_first_sentence(c['summary'])} {' '.join(rel)}")
    xs = [c for c in pool.values() if c["url"].startswith("https://x.com/")]
    rest = [c for c in pool.values() if not c["url"].startswith("https://x.com/")]
    return "\n".join(line(c) for c in xs + rest)


def assemble(brief: Brief, pool: dict[int, dict], hot: float) -> list[dict]:
    used: set[int] = set()
    stories = []
    for st in brief.stories:
        if st.primary_id not in pool or st.primary_id in used:
            continue
        ids = [st.primary_id] + [i for i in dict.fromkeys(st.supporting_ids) if i in pool and i not in used
                                 and i != st.primary_id][:4]
        used.update(ids)
        stories.append({
            "headline": st.headline.strip(), "why": st.why.strip(),
            "hot": max(pool[i]["rel"] for i in ids) >= hot,
            "links": [{"label": link_label(pool[i]), "url": pool[i]["url"], "item_id": i, "type": pool[i]["type"]}
                      for i in ids],
        })
        if len(stories) == 10:
            break
    return stories


async def make_brief(since: datetime | None = None, until: datetime | None = None, save: bool = True) -> dict | None:
    cfg = settings()
    until = until or datetime.now(UTC)
    if since is None:
        last = await db.fetchrow("select max(window_end) as t from briefs")
        since = (last and last["t"]) or until - timedelta(days=cfg.lookback_days)
    pool = await candidates(since, until)
    if not pool:
        return None
    llm = get_llm(cfg.brief_model)
    system = SYSTEM.format(auki=(PROMPTS / "auki_context.md").read_text())
    window = f"Period: {since:%Y-%m-%d %H:%M} to {until:%Y-%m-%d %H:%M} UTC. {len(pool)} candidates:\n\n"
    brief, cost = await llm.structured(system, window + candidate_lines(pool), Brief)
    stories = assemble(brief, pool, cfg.alert_min_relevance)
    counts = {r["source"]: r["n"] for r in await db.fetch(
        """select source, count(distinct item_id) as n from item_sources
           where seen_at >= %s and seen_at < %s group by 1 order by 2 desc""", since, until)}
    n_new = await db.fetchrow("select count(*) as n from items where ingested_at >= %s and ingested_at < %s", since, until)
    out = {"window_start": since, "window_end": until, "n_candidates": len(pool), "n_new_items": n_new["n"],
           "model": llm.model, "cost_usd": round(cost, 5), "stories": stories, "sources": counts}
    if save:
        row = await db.fetchrow(
            """insert into briefs (window_start, window_end, n_candidates, n_new_items, model, cost_usd, stories, sources)
               values (%s, %s, %s, %s, %s, %s, %s, %s) returning id, created_at""",
            since, until, len(pool), n_new["n"], llm.model, round(cost, 6), Jsonb(stories), Jsonb(counts))
        out.update(id=row["id"], created_at=row["created_at"])
    log.info("brief.made", stories=len(stories), candidates=len(pool), cost=round(cost, 4))
    return out


async def latest(n: int = 1) -> list[dict]:
    return await db.fetch("select * from briefs order by created_at desc limit %s", n)
