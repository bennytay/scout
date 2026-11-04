"""Reference connector: any RSS/Atom feed. This is the template for adding a new source."""
from datetime import UTC, datetime
from time import mktime

import feedparser

from ..models import Item
from ..urls import guess_type
from .base import Connector, register


@register
class RSSConnector(Connector):
    name = "rss"
    kinds = ("rss",)

    async def fetch(self, http, kind, value, since):
        r = await http.get(value)
        r.raise_for_status()
        items = []
        for e in feedparser.parse(r.content).entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            published = datetime.fromtimestamp(mktime(ts), tz=UTC) if ts else None
            if published and published < since:
                continue
            items.append(Item(
                url=e.link, type=guess_type(e.link), title=e.title, source="rss", source_ref=value,
                summary=e.get("summary"), published_at=published,
                authors=[a.name for a in e.get("authors", []) if a.get("name")],
            ))
        return items
