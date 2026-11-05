"""X (Twitter) via the official X API v2 (pay-per-use credits). X is Scout's newsroom.

One scan = a handful of recent-search requests, not one per account:
- radar:     curated `x_account` rows packed into `(from:a OR from:b …)` queries under the 512-char limit
- discovery: `x_query` rows, link-anchored searches (posts from anyone that point at research). They read a
             window that ends X_DISCOVERY_DELAY_HOURS ago, so posts have had time to collect likes before the gate.
Each source keeps `until` in `sources.cursor`, so posts are paid for once. The gate (xsignal.py) runs before
any LLM. Auth: X_BEARER_TOKEN, or X_API_KEY + X_API_SECRET exchanged once for an app-only bearer token.
Shared X links in Discord resolve via the free fxtwitter embed API first, then the X API as fallback.
"""
import re
from datetime import UTC, datetime, timedelta

import httpx

from .. import xsignal
from ..config import settings
from ..log import log
from ..models import Item, ItemType
from .base import Connector, FetchResult, register

API = "https://api.x.com/2"
FX = "https://api.fxtwitter.com/status/{id}"
TWEET_FIELDS = "created_at,public_metrics,entities,author_id,note_tweet"
USER_FIELDS = "name,username,public_metrics,created_at,verified_type,profile_image_url"
COMMON = {"tweet.fields": TWEET_FIELDS, "expansions": "author_id,attachments.media_keys", "user.fields": USER_FIELDS,
          "media.fields": "url,preview_image_url,type"}
RADAR_SUFFIX = "-is:retweet -is:reply"
DISCOVERY_SUFFIX = "-is:retweet -is:reply lang:en"
QUERY_LIMIT = 512  # verified against the API: "query length must be <= 512"
_bearer: str | None = None


async def bearer(http: httpx.AsyncClient) -> str:
    global _bearer
    cfg = settings()
    if cfg.x_bearer_token:
        return cfg.x_bearer_token
    if not _bearer:
        r = await http.post("https://api.x.com/oauth2/token", auth=(cfg.x_api_key, cfg.x_api_secret),
                            data={"grant_type": "client_credentials"})
        r.raise_for_status()
        _bearer = r.json()["access_token"]
    return _bearer


async def _headers(http: httpx.AsyncClient) -> dict:
    return {"Authorization": f"Bearer {await bearer(http)}"}


def post_title(text: str, handle: str) -> str:
    """Readable title from a post: whole text, links stripped, whitespace collapsed, cut at a word."""
    t = " ".join(re.sub(r"https?://\S+", "", text).split())
    if len(t) > 120:
        t = t[:120].rsplit(" ", 1)[0] + "…"
    return f"@{handle}: {t}" if t else f"Post by @{handle}"


def _user_metrics(user: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    if pm := user.get("public_metrics"):
        out["x_followers"] = pm.get("followers_count", 0)
    if created := user.get("created_at"):
        age = datetime.now(UTC) - datetime.fromisoformat(created.replace("Z", "+00:00"))
        out["x_account_age_days"] = age.days
    if user.get("verified_type"):
        out["x_verified"] = 0.0 if user["verified_type"] == "none" else 1.0
    return out


def _media(t: dict, user: dict, media: dict[str, dict]) -> dict[str, str]:
    """The post's first photo (or video thumbnail) and the poster's avatar, for the brief's cards."""
    out = {}
    for key in (t.get("attachments") or {}).get("media_keys", []):
        m = media.get(key) or {}
        if url := m.get("url") or m.get("preview_image_url"):
            out["image"] = url
            break
    if avatar := user.get("profile_image_url"):
        out["avatar"] = avatar.replace("_normal.", "_bigger.")
    return out


def tweet_item(t: dict, users: dict[str, dict], source: str = "x", source_ref: str | None = None,
               media: dict[str, dict] | None = None) -> Item:
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
                 "x_quotes": m.get("quote_count", 0), "x_impressions": m.get("impression_count", 0),
                 **_user_metrics(user)},
        outlinks=list(dict.fromkeys(links)),
        media=_media(t, user, media or {}),
    )


def parse_page(data: dict, source_ref: str | None = None) -> list[Item]:
    inc = data.get("includes") or {}
    users = {u["id"]: u for u in inc.get("users", [])}
    media = {m["media_key"]: m for m in inc.get("media", [])}
    return [tweet_item(t, users, source_ref=source_ref, media=media) for t in data.get("data") or []]


def fx_media(t: dict) -> dict[str, str]:
    """Image + avatar from an fxtwitter `tweet` object (free; used for shared links and the backfill)."""
    out = {}
    m = t.get("media") or {}
    if photos := m.get("photos"):
        out["image"] = photos[0].get("url")
    elif videos := m.get("videos"):
        out["image"] = videos[0].get("thumbnail_url")
    if avatar := (t.get("author") or {}).get("avatar_url"):
        out["avatar"] = avatar
    return {k: v for k, v in out.items() if v}


async def resolve_post(http: httpx.AsyncClient, url: str) -> Item | None:
    m = re.search(r"/status/(\d+)", url)
    if not m:
        return None
    r = await http.get(FX.format(id=m.group(1)))  # free path first: saves API credits
    if r.status_code == 200 and (t := r.json().get("tweet")):
        links = [f.get("original") or f.get("url") for f in (t.get("raw_text") or {}).get("facets", [])
                 if f.get("type") == "url"]
        author = t.get("author") or {}
        item = tweet_item({
            "id": t["id"], "text": t.get("text"), "author_id": "a",
            "created_at": datetime.fromtimestamp(t["created_timestamp"], tz=UTC).isoformat()
            if t.get("created_timestamp") else None,
            "public_metrics": {"like_count": t.get("likes", 0), "retweet_count": t.get("retweets", 0)},
            "entities": {"urls": [{"expanded_url": l} for l in links if l]},
        }, {"a": {"username": author.get("screen_name"), "name": author.get("name")}})
        return item.model_copy(update={"media": fx_media(t)})
    if settings().x_enabled:
        r = await http.get(f"{API}/tweets/{m.group(1)}", params=COMMON, headers=await _headers(http))
        if r.status_code == 200:
            d = r.json()
            return parse_page({"data": [d["data"]], "includes": d.get("includes")})[0]
    return None


async def search(http: httpx.AsyncClient, query: str, start: datetime, end: datetime, cap: int) -> list[Item]:
    """Recent search over [start, end), following next_token until `cap` posts."""
    items: list[Item] = []
    params = {**COMMON, "query": query, "max_results": min(100, max(10, cap)),
              "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end_time": end.strftime("%Y-%m-%dT%H:%M:%SZ")}
    while len(items) < cap:
        r = await http.get(f"{API}/tweets/search/recent", params=params, headers=await _headers(http))
        r.raise_for_status()
        data = r.json()
        items += parse_page(data)
        token = (data.get("meta") or {}).get("next_token")
        if not token:
            break
        params["next_token"] = token
    return items[:cap]


def _window_start(state: dict, default: datetime, now: datetime) -> datetime:
    start = datetime.fromisoformat(state["until"]) if state.get("until") else default
    return max(start, now - timedelta(days=6, hours=23))  # recent search covers the last 7 days


@register
class XConnector(Connector):
    name = "x"
    kinds = ("x_account", "x_query")
    needs = ("x_enabled",)

    async def fetch_many(self, http, sources, since) -> FetchResult:
        cfg = settings()
        now = datetime.now(UTC).replace(microsecond=0)
        out = FetchResult()
        raw: list[Item] = []

        # 1. radar: pack accounts into a few from: queries
        radar = {s["value"].lstrip("@").lower(): s for s in sources if s["kind"] == "x_account"}
        end = now - timedelta(seconds=30)
        for batch in xsignal.batch_queries(list(radar), RADAR_SUFFIX, QUERY_LIMIT):
            rows = [radar[h] for h in batch]
            start = min(_window_start(dict(r["cursor"] or {}), since, now) for r in rows)
            try:
                got = await search(http, xsignal.radar_query(batch, RADAR_SUFFIX), start, end, cfg.x_max_results)
            except Exception as e:
                msg = f"radar batch ({batch[0]}…): {e!r}"[:300]
                out.errors.append(msg)
                out.failed.update({r["id"]: msg for r in rows})
                continue
            raw += got
            for r in rows:
                out.states[r["id"]] = {**(r["cursor"] or {}), "until": end.isoformat()}

        # 2. discovery: link-anchored searches, read with a delay so engagement has accrued
        d_end = now - timedelta(hours=cfg.x_discovery_delay_hours)
        for s in (s for s in sources if s["kind"] == "x_query"):
            state = dict(s["cursor"] or {})
            start = _window_start(state, max(since, d_end - timedelta(hours=24)), now)
            if d_end - start < timedelta(minutes=10):
                continue
            try:
                got = await search(http, f"({s['value']}) {DISCOVERY_SUFFIX}", start, d_end, cfg.x_max_results)
            except Exception as e:
                msg = f"x_query:{s['value'][:60]}: {e!r}"[:300]
                out.errors.append(msg)
                out.failed[s["id"]] = msg
                continue
            tier = (s.get("config") or {}).get("tier", "discovery")
            raw += [i.model_copy(update={"source_ref": tier}) for i in got]
            out.states[s["id"]] = {**state, "until": d_end.isoformat()}

        # 3. gate (free) before anything reaches the LLM
        unique: dict[str, Item] = {}
        for i in raw:  # first sighting wins: radar, then research discovery, then the stricter news search
            unique.setdefault(i.url, i)
        unique = list(unique.values())
        out.seen = len(unique)
        out.items, out.dropped = xsignal.gate_batch(unique, set(radar), now)
        log.info("x.gate", seen=out.seen, kept=len(out.items), dropped=dict(out.dropped))
        return out
