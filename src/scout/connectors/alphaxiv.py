"""alphaXiv 'hot' feed: a trending/attention signal. Unofficial API, so everything fails soft."""
import re
from datetime import datetime

from ..log import log
from ..models import Item, ItemType
from .base import Connector, register

API = "https://api.alphaxiv.org/papers/v3/feed"
ROBOTICS = re.compile(r"robot|embodied|manipulat|locomot|humanoid|slam|navigation|spatial|vision-language-action|"
                      r"autonomous|grasp|sim2real|3d|mapping|locali", re.IGNORECASE)
ARXIV = re.compile(r"^(\d{4}\.\d{4,5})")


def paper_item(p: dict) -> Item | None:
    m = ARXIV.match(p.get("universal_paper_id") or "")
    if not m:
        return None  # non-arXiv entries (blog posts) have no stable canonical URL
    text = " ".join([p.get("title", ""), p.get("abstract", ""), " ".join(p.get("topics") or [])])
    if not ROBOTICS.search(text):
        return None
    pub = p.get("first_publication_date") or p.get("publication_date")
    metrics = p.get("metrics") or {}
    return Item(
        url=f"https://arxiv.org/abs/{m.group(1)}", type=ItemType.paper, title=p["title"],
        summary=p.get("abstract"), published_at=datetime.fromisoformat(pub) if pub else None,
        source="alphaxiv", source_ref=p.get("id"), arxiv_id=m.group(1), authors=p.get("authors") or [],
        metrics={"ax_votes": metrics.get("public_total_votes") or 0,
                 "ax_visits_7d": (metrics.get("visits_count") or {}).get("last_7_days") or 0},
        outlinks=[u for u in [p.get("github_url")] if u],
    )


@register
class AlphaXivConnector(Connector):
    name = "alphaxiv"
    kinds = ("alphaxiv",)

    async def fetch(self, http, kind, value, since):
        try:
            r = await http.get(API, params={"pageNum": 0, "sort": "Hot", "pageSize": 100, "interval": "7 Days"})
            r.raise_for_status()
            papers = r.json().get("papers", [])
        except Exception as e:  # optional source: never break the run
            log.warning("alphaxiv.unavailable", error=str(e))
            return []
        return [i for p in papers if (i := paper_item(p))]
