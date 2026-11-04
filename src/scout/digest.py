"""Weekly digest + draft X posts (human approval required, never auto-published)."""
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from . import db
from . import search as s
from .providers.llm import get_llm

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


class Drafts(BaseModel):
    posts: list[str] = Field(description="2-3 draft X posts, each ≤270 chars including the item's URL.")
    item_ids: list[int] = Field(description="The item id each post is about, same order as posts.")


DIGEST_SYSTEM = """Write a weekly robotics digest for the Auki Labs team (Discord markdown, ≤ 1800 chars).
Structure: a one-line headline of the week; 4-6 bullets of the most important items, each `**Title**: one
sentence on what's new and why it matters to Auki` followed by the URL in <>; then a one-line "Worth watching".
Use only the items provided."""


def _items_block(items: list[dict]) -> str:
    return "\n".join(
        f"- id={i['id']} | {i['title']} | {i['url']} | topics={','.join(i.get('topics', []))} | "
        f"relevance={i.get('auki_relevance', '?')} | {i.get('summary', '')[:300]} | why: {i.get('auki_relevance_reason', '')}"
        for i in items)


async def weekly(days: int = 7, save_drafts: bool = True) -> dict:
    d = await s.digest(days)
    pool = {i["id"]: i for i in d["most_relevant_to_auki"] + d["trending"]}
    items = list(pool.values())[:12]
    if not items:
        return {"digest": "Quiet week: nothing new ingested.", "drafts": [], "cost_usd": 0.0}
    llm = get_llm()
    text, c1 = await llm.text(DIGEST_SYSTEM, f"Stats: {d['stats']}\nBy topic: {d['by_topic']}\n\nItems:\n"
                              + _items_block(items), max_tokens=1500)
    voice = (PROMPTS / "auki_voice.md").read_text()
    drafts, c2 = await llm.structured(voice, "Draft 2-3 posts about the best of these items:\n"
                                      + _items_block(items[:6]), Drafts)
    week_of = date.today() - timedelta(days=date.today().weekday())
    saved = []
    for n, body in enumerate(drafts.posts[:3]):
        iid = drafts.item_ids[n] if n < len(drafts.item_ids) and drafts.item_ids[n] in pool else items[0]["id"]
        row = None
        if save_drafts:
            row = await db.fetchrow("insert into post_drafts (week_of, body, item_ids) values (%s, %s, %s) returning id",
                                    week_of, body, [iid])
        saved.append({"id": row["id"] if row else None, "body": body, "item_id": iid})
    return {"digest": text, "drafts": saved, "cost_usd": round(c1 + c2, 5), "stats": d["stats"]}
