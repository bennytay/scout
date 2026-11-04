from datetime import UTC, datetime

from ..models import Item
from ..urls import guess_type
from .base import Connector, register

API = "https://hn.algolia.com/api/v1/search_by_date"


def hit_item(h: dict) -> Item:
    hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
    url = h.get("url") or hn_url
    return Item(
        url=url, type=guess_type(url), title=h.get("title") or "", summary=h.get("story_text"),
        published_at=datetime.fromtimestamp(h["created_at_i"], tz=UTC), source="hackernews",
        source_ref=h["objectID"],
        metrics={"hn_points": h.get("points") or 0, "hn_comments": h.get("num_comments") or 0},
        outlinks=[hn_url] if url != hn_url else [],
    )


@register
class HackerNewsConnector(Connector):
    name = "hackernews"
    kinds = ("hn_query",)

    async def fetch(self, http, kind, value, since):
        r = await http.get(API, params={
            "query": value, "tags": "story", "hitsPerPage": 50,
            "typoTolerance": "false", "restrictSearchableAttributes": "title,url",  # "robot" != "Robert"
            "numericFilters": f"created_at_i>{int(since.timestamp())},points>=15",
        })
        r.raise_for_status()
        return [hit_item(h) for h in r.json()["hits"] if h.get("title")]
