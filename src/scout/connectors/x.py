"""X (Twitter).

Two paths, neither needs the paid X API:
  1. Monitoring tracked accounts/queries via xAI's API (Grok with its X-search tool). Needs XAI_API_KEY.
  2. Resolving individual X links shared in Discord via the public fxtwitter embed API (no key).
"""
import json
import re
from datetime import UTC, datetime

import httpx

from ..config import settings
from ..log import log
from ..models import Item, ItemType
from ..urls import find_urls
from .base import Connector, register

XAI = "https://api.x.ai/v1/responses"
FX = "https://api.fxtwitter.com/status/{id}"

PROMPT = """Search X for posts {what} published since {since}.
Only include posts about robotics research or products: papers, code releases, models, datasets, demos.
Return ONLY a JSON array (no prose), max 25 objects:
[{{"url": "https://x.com/<handle>/status/<id>", "handle": "...", "text": "full post text",
   "created_at": "ISO-8601", "likes": 0, "reposts": 0, "links": ["urls in the post"]}}]"""


def post_item(p: dict, source: str = "x", source_ref: str | None = None) -> Item | None:
    url = p.get("url") or ""
    m = re.search(r"x\.com/([^/]+)/status/(\d+)", url) or re.search(r"twitter\.com/([^/]+)/status/(\d+)", url)
    if not m:
        return None
    text = p.get("text") or ""
    created = p.get("created_at")
    try:
        published = datetime.fromisoformat(created) if created else None
    except ValueError:
        published = None
    return Item(
        url=f"https://x.com/{m.group(1)}/status/{m.group(2)}", type=ItemType.post,
        title=(text.split("\n")[0][:140] or f"Post by @{m.group(1)}"), summary=text, full_text=text,
        published_at=published, source=source, source_ref=source_ref or m.group(2),
        authors=[p.get("author_name") or m.group(1)], author_handles={"x": m.group(1)},
        metrics={"x_likes": p.get("likes") or 0, "x_reposts": p.get("reposts") or 0},
        outlinks=list(dict.fromkeys((p.get("links") or []) + find_urls(text))),
    )


def _output_text(data: dict) -> str:
    if data.get("output_text"):
        return data["output_text"]
    parts = []
    for o in data.get("output", []):
        for c in o.get("content", []) or []:
            if c.get("type") in ("output_text", "text"):
                parts.append(c.get("text", ""))
    return "".join(parts)


def parse_grok(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else []
    except json.JSONDecodeError:
        return []


async def resolve_post(http: httpx.AsyncClient, url: str) -> Item | None:
    m = re.search(r"/status/(\d+)", url)
    if not m:
        return None
    r = await http.get(FX.format(id=m.group(1)))
    if r.status_code != 200:
        return None
    t = r.json().get("tweet") or {}
    links = [f.get("original") or f.get("url") for f in (t.get("raw_text") or {}).get("facets", []) if f.get("type") == "url"]
    return post_item({
        "url": t.get("url", url), "text": t.get("text"), "likes": t.get("likes"), "reposts": t.get("retweets"),
        "author_name": (t.get("author") or {}).get("name"),
        "created_at": datetime.fromtimestamp(t["created_timestamp"], tz=UTC).isoformat()
        if t.get("created_timestamp") else None,
        "links": [l for l in links if l],
    })


@register
class XConnector(Connector):
    name = "x"
    kinds = ("x_account", "x_query")
    needs = ("xai_api_key",)

    async def fetch(self, http, kind, value, since):
        s = settings()
        what = f"from @{value.lstrip('@')}" if kind == "x_account" else f'matching "{value}"'
        tool: dict = {"type": "x_search", "from_date": since.date().isoformat()}
        if kind == "x_account":
            tool["allowed_x_handles"] = [value.lstrip("@")]
        r = await http.post(
            XAI, timeout=120,
            headers={"Authorization": f"Bearer {s.xai_api_key}"},
            json={"model": s.xai_model, "tools": [tool],
                  "input": [{"role": "user", "content": PROMPT.format(what=what, since=since.date())}]},
        )
        r.raise_for_status()
        posts = parse_grok(_output_text(r.json()))
        log.info("x.grok", query=value, posts=len(posts))
        return [i for p in posts if (i := post_item(p, source_ref=value))]
