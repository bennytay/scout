import asyncio
from datetime import UTC, datetime
from time import mktime

import feedparser
import httpx

from ..config import settings
from ..models import Item, ItemType
from ..urls import arxiv_id_from
from .base import Connector, register

API = "https://export.arxiv.org/api/query"


def parse_feed(xml: str) -> list[Item]:
    items = []
    for e in feedparser.parse(xml).entries:
        aid = arxiv_id_from(e.get("id", ""))
        if not aid:
            continue
        published = datetime.fromtimestamp(mktime(e.published_parsed), tz=UTC) if e.get("published_parsed") else None
        items.append(
            Item(
                url=f"https://arxiv.org/abs/{aid}",
                type=ItemType.paper,
                title=" ".join(e.title.split()),
                summary=" ".join(e.get("summary", "").split()),
                published_at=published,
                source="arxiv",
                source_ref=aid,
                arxiv_id=aid,
                doi=(e.get("arxiv_doi") or None),
                authors=[a.name for a in e.get("authors", [])],
                outlinks=[l.href for l in e.get("links", []) if "github.com" in l.get("href", "")],
                metrics={},
            )
        )
    return items


async def fetch_ids(http: httpx.AsyncClient, ids: list[str]) -> list[Item]:
    r = await http.get(API, params={"id_list": ",".join(ids), "max_results": len(ids)})
    r.raise_for_status()
    return parse_feed(r.text)


@register
class ArxivConnector(Connector):
    name = "arxiv"
    kinds = ("arxiv_category", "arxiv_query")

    async def fetch(self, http, kind, value, since):
        query = f"cat:{value}" if kind == "arxiv_category" else value
        out: list[Item] = []
        cap = settings().max_items_per_source * 2
        for start in range(0, cap, 100):
            r = await http.get(API, params={
                "search_query": query, "sortBy": "submittedDate", "sortOrder": "descending",
                "start": start, "max_results": 100,
            })
            r.raise_for_status()
            page = parse_feed(r.text)
            out += [i for i in page if not i.published_at or i.published_at >= since]
            if len(page) < 100 or (page[-1].published_at and page[-1].published_at < since):
                break
            await asyncio.sleep(3)  # arXiv API etiquette
        return out
