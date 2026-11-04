"""X (Twitter) via the official X API v2 (pay-per-use credits).

- x_account: a user's recent posts (no retweets/replies)
- x_query:   recent search, restricted to posts with links (papers/repos/demos), English, no retweets/replies
Incremental: the user id and newest post id are kept in `sources.cursor`, so each run only pays for new posts.
Shared X links in Discord resolve via the free fxtwitter embed API first, then the X API as fallback.
"""
import re
from datetime import UTC, datetime

import httpx

from ..config import settings
from ..models import Item, ItemType
from .base import Connector, register

API = "https://api.x.com/2"
FX = "https://api.fxtwitter.com/status/{id}"
TWEET_FIELDS = "created_at,public_metrics,entities,author_id,note_tweet"
COMMON = {"tweet.fields": TWEET_FIELDS, "expansions": "author_id", "user.fields": "name,username"}


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings().x_bearer_token}"}


def post_title(text: str, handle: str) -> str:
    """Readable title from a post: whole text, links stripped, whitespace collapsed, cut at a word."""
    t = " ".join(re.sub(r"https?://\S+", "", text).split())
    if len(t) > 120:
        t = t[:120].rsplit(" ", 1)[0] + "…"
    return f"@{handle}: {t}" if t else f"Post by @{handle}"


def tweet_item(t: dict, users: dict[str, dict], source: str = "x", source_ref: str | None = None) -> Item:
    user = users.get(t.get("author_id"), {})
    handle = user.get("username") or "i"
    text = (t.get("note_tweet") or {}).get("text") or t.get("text") or ""
    m = t.get("public_metrics") or {}
    links = [u.get("unwound_url") or u.get("expanded_url") for u in (t.get("entities") or {}).get("urls", [])]
    links = [u for u in links if u and not re.match(r"https?://(x|twitter)\.com/.+/(photo|video)/", u)]
    return Item(
        url=f"https://x.com/{handle}/status/{t['id']}", type=ItemType.post,
        title=post_title(text, handle), summary=text, full_text=text,
        published_at=datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")) if t.get("created_at") else None,
        source=source, source_ref=source_ref or t["id"],
        authors=[user.get("name") or handle], author_handles={"x": handle},
        metrics={"x_likes": m.get("like_count", 0), "x_reposts": m.get("retweet_count", 0),
                 "x_quotes": m.get("quote_count", 0), "x_impressions": m.get("impression_count", 0)},
        outlinks=list(dict.fromkeys(links)),
    )


def parse_page(data: dict, source_ref: str | None = None) -> list[Item]:
    users = {u["id"]: u for u in (data.get("includes") or {}).get("users", [])}
    return [tweet_item(t, users, source_ref=source_ref) for t in data.get("data") or []]


async def resolve_post(http: httpx.AsyncClient, url: str) -> Item | None:
    m = re.search(r"/status/(\d+)", url)
    if not m:
        return None
    r = await http.get(FX.format(id=m.group(1)))  # free path first: saves API credits
    if r.status_code == 200 and (t := r.json().get("tweet")):
        links = [f.get("original") or f.get("url") for f in (t.get("raw_text") or {}).get("facets", [])
                 if f.get("type") == "url"]
        author = t.get("author") or {}
        return tweet_item({
            "id": t["id"], "text": t.get("text"), "author_id": "a",
            "created_at": datetime.fromtimestamp(t["created_timestamp"], tz=UTC).isoformat()
            if t.get("created_timestamp") else None,
            "public_metrics": {"like_count": t.get("likes", 0), "retweet_count": t.get("retweets", 0)},
            "entities": {"urls": [{"expanded_url": l} for l in links if l]},
        }, {"a": {"username": author.get("screen_name"), "name": author.get("name")}})
    if settings().x_bearer_token:
        r = await http.get(f"{API}/tweets/{m.group(1)}", params=COMMON, headers=_headers())
        if r.status_code == 200:
            d = r.json()
            return parse_page({"data": [d["data"]], "includes": d.get("includes")})[0]
    return None


@register
class XConnector(Connector):
    name = "x"
    kinds = ("x_account", "x_query")
    needs = ("x_bearer_token",)
    stateful = True

    async def fetch(self, http, kind, value, since, state=None):
        state = state if state is not None else {}
        params = {**COMMON, "max_results": settings().x_max_results}
        if state.get("since_id"):
            params["since_id"] = state["since_id"]
        else:
            params["start_time"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        if kind == "x_account":
            handle = value.lstrip("@")
            if not state.get("user_id"):
                r = await http.get(f"{API}/users/by/username/{handle}", headers=_headers())
                r.raise_for_status()
                state["user_id"] = r.json()["data"]["id"]
            r = await http.get(f"{API}/users/{state['user_id']}/tweets",
                               params={**params, "exclude": "retweets,replies"}, headers=_headers())
        else:
            q = f"({value}) has:links -is:retweet -is:reply lang:en"
            r = await http.get(f"{API}/tweets/search/recent", params={**params, "query": q}, headers=_headers())
        r.raise_for_status()
        data = r.json()
        if newest := (data.get("meta") or {}).get("newest_id"):
            state["since_id"] = newest
        return parse_page(data, source_ref=value)
