from datetime import datetime, timedelta

from ..config import settings
from ..models import Item, ItemType
from .base import Connector, register

API = "https://huggingface.co/api"


def _dt(s):
    return datetime.fromisoformat(s) if s else None


def daily_paper_item(d: dict) -> Item:
    p = d.get("paper", d)
    aid = p["id"]
    return Item(
        url=f"https://arxiv.org/abs/{aid}", type=ItemType.paper, title=" ".join(p["title"].split()),
        summary=p.get("summary"), published_at=_dt(p.get("publishedAt")), source="huggingface",
        source_ref=f"daily:{aid}", arxiv_id=aid,
        authors=[a["name"] for a in p.get("authors", []) if a.get("name")],
        metrics={"hf_upvotes": p.get("upvotes", 0)},
        outlinks=[u for u in [p.get("githubRepo"), p.get("projectPage")] if u],
    )


def hub_item(x: dict, kind: str) -> Item:
    rid = x["id"]
    url = f"https://huggingface.co/{'datasets/' if kind == 'datasets' else ''}{rid}"
    return Item(
        url=url, type=ItemType.dataset if kind == "datasets" else ItemType.model, title=rid,
        summary=(x.get("cardData") or {}).get("description") if isinstance(x.get("cardData"), dict) else None,
        published_at=_dt(x.get("createdAt")), source="huggingface", source_ref=f"{kind}:{rid}",
        # The owner may be an individual (e.g. "lyl472324464"), so it is a handle, not an org.
        # Real orgs are extracted by the enrichment LLM from the model card.
        author_handles={"hf": rid.split("/")[0]} if "/" in rid else {},
        metrics={"hf_likes": x.get("likes", 0), "hf_downloads": x.get("downloads", 0)},
    )


@register
class HuggingFaceConnector(Connector):
    name = "huggingface"
    kinds = ("hf_feed",)

    async def fetch(self, http, kind, value, since):
        headers = {"Authorization": f"Bearer {settings().hf_token}"} if settings().hf_token else {}
        if value == "daily_papers":
            out, day = [], datetime.now(since.tzinfo).date()
            while day >= since.date():
                r = await http.get(f"{API}/daily_papers", params={"date": day.isoformat()}, headers=headers)
                if r.status_code == 200:
                    out += [daily_paper_item(d) for d in r.json()]
                day -= timedelta(days=1)
            return out
        kind_, _, arg = value.partition(":")  # models:robotics  |  datasets:lerobot
        params = {"sort": "createdAt", "direction": -1, "limit": 50}
        if kind_ == "models":
            params["pipeline_tag"] = arg
        else:
            params["search"] = arg
        r = await http.get(f"{API}/{kind_}", params=params, headers=headers)
        r.raise_for_status()
        return [hub_item(x, kind_) for x in r.json() if (_dt(x.get("createdAt")) or since) >= since]
