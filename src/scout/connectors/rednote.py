"""RedNote (小红书 / Xiaohongshu) via a self-hosted xiaohongshu-mcp server (github.com/xpzouying/xiaohongshu-mcp).

RedNote has no public API. xiaohongshu-mcp drives a logged-in RedNote web session in a headless browser and
exposes it as MCP *and* plain REST on :18060. Scout uses the REST side:

  POST /api/v1/feeds/search   {"keyword", "filters": {"sort_by", "note_type", "publish_time"}}
                              -> {"success", "data": {"feeds": [Feed], "count"}}
  POST /api/v1/feeds/detail   {"feed_id", "xsec_token"}
                              -> {"success", "data": {"feed_id", "data": {"note": FeedDetail, "comments"}}}
  GET  /api/v1/login/status   -> {"success", "data": {"is_logged_in", "username"}}

A search returns one page of cards (title, poster, likes, cover), with no body text and no date. So the funnel is:
  1. search    `rednote_query` rows (Chinese + English research keywords), newest week only
  2. gate      (free, on the card) spam lexicon, likes, per-author cap, copy-paste titles, already seen
  3. detail    only for cards that pass: body text, date, tags, images. One browser page load each, so capped.
  4. judge     the shared enrichment call: English summary + headline, signal (promo/off_topic/noise dropped)
  5. expand    arXiv / GitHub / project links written in the note body are fetched and linked, as for X.
Each query's source cursor remembers the note ids it has already handled, so a note is opened once.
"""
import hashlib
import re
from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx

from ..config import settings
from ..log import log
from ..models import Item, ItemType
from ..urls import find_urls
from .base import Connector, FetchResult, register

NOTE_URL = "https://www.xiaohongshu.com/explore/{id}"
SEEN_KEEP = 600  # note ids remembered per query

# Selling, coursework-for-hire, lead generation. RedNote's robotics tag is full of it.
SPAM = re.compile(
    r"代做|代写|代跑|毕设|毕业设计|课设|接单|辅导|带教|保过|私信|私我|滴滴我|加[vV微]|[vV][xX]|微信|wx|"
    r"课程|网课|训练营|培训|招生|报名|优惠|折扣|团购|返现|领取|免费送|包邮|下单|购买|出售|转让|二手|闲鱼|"
    r"拼多多|淘宝|链接在|主页简介|求职|内推|招聘|面经|上岸|airdrop|giveaway|link in bio", re.I)
CJK = re.compile(r"[㐀-鿿豈-﫿]")
TOPIC_TAG = re.compile(r"#([^#\[\]\s]+)(?:\[话题\])?#?")


def has_cjk(text: str | None) -> bool:
    return bool(CJK.search(text or ""))


def count(v) -> int:
    """RedNote counts are display strings: '892', '1.2万', '10万+', '3k', '' -> ints."""
    if isinstance(v, int | float):
        return int(v)
    s = str(v or "").strip().lower().rstrip("+")
    if not s:
        return 0
    mult = 1
    for suffix, m in (("万", 10_000), ("w", 10_000), ("亿", 100_000_000), ("k", 1_000)):
        if s.endswith(suffix):
            s, mult = s[: -len(suffix)], m
            break
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


def _nick(user: dict) -> str:
    return user.get("nickname") or user.get("nickName") or "rednote"


def note_title(display_title: str, nick: str) -> str:
    t = " ".join((display_title or "").split())
    if len(t) > 120:
        t = t[:120] + "…"
    return f"@{nick}: {t}" if t else f"RedNote note by @{nick}"


def card_item(feed: dict, query: str = "") -> Item | None:
    """A search-result card -> Item (no body yet). Returns None for non-note cards (live rooms, hot queries)."""
    if feed.get("modelType", "note") != "note" or not feed.get("id"):
        return None
    card = feed.get("noteCard") or {}
    user = card.get("user") or {}
    info = card.get("interactInfo") or {}
    cover = card.get("cover") or {}
    title = card.get("displayTitle") or ""
    media = {k: v for k, v in {"image": cover.get("urlDefault") or cover.get("url"),
                                "avatar": user.get("avatar")}.items() if v}
    if token := feed.get("xsecToken"):  # a note only opens in a browser with its token
        media["link"] = f"{NOTE_URL.format(id=feed['id'])}?xsec_token={token}&xsec_source=pc_search"
    return Item(
        url=NOTE_URL.format(id=feed["id"]), type=ItemType.post, title=note_title(title, _nick(user)),
        summary=title, full_text=title, source="rednote", source_ref=query or feed["id"],
        authors=[_nick(user)], author_handles={"rednote": user.get("userId") or ""},
        metrics={"xhs_likes": count(info.get("likedCount")), "xhs_collects": count(info.get("collectedCount")),
                 "xhs_comments": count(info.get("commentCount")), "xhs_shares": count(info.get("sharedCount"))},
        media=media,
    )


def clean_desc(desc: str) -> str:
    """'#具身智能[话题]# #机器人[话题]#' -> '#具身智能 #机器人'."""
    return TOPIC_TAG.sub(lambda m: f"#{m.group(1)} ", desc or "").strip()


def with_detail(item: Item, note: dict) -> Item:
    """Merge a FeedDetail (body, date, images, fresher counts) into the card's Item."""
    desc = clean_desc(note.get("desc") or "")
    title = note.get("title") or item.summary or ""
    info = note.get("interactInfo") or {}
    metrics = {**item.metrics, **{k: count(info.get(f)) for k, f in (
        ("xhs_likes", "likedCount"), ("xhs_collects", "collectedCount"),
        ("xhs_comments", "commentCount"), ("xhs_shares", "sharedCount")) if info.get(f)}}
    media = dict(item.media)
    if (imgs := note.get("imageList")) and imgs[0].get("urlDefault"):
        media["image"] = imgs[0]["urlDefault"]
    text = f"{title}\n\n{desc}".strip()
    if note.get("ipLocation"):
        text += f"\n\n(posted from {note['ipLocation']})"
    return item.model_copy(update={
        "title": note_title(title, item.authors[0] if item.authors else "rednote"),
        "summary": desc[:1500] or title, "full_text": text, "metrics": metrics, "media": media,
        "published_at": datetime.fromtimestamp(note["time"] / 1000, tz=UTC) if note.get("time") else None,
        "outlinks": find_urls(desc),
    })


def _fingerprint(item: Item) -> str:
    words = re.findall(r"[a-z0-9]+|[㐀-鿿]", (item.summary or item.title).lower())
    return hashlib.md5("".join(words[:40]).encode()).hexdigest()


def gate(item: Item) -> str | None:
    """Why a card should be dropped before we pay for its detail page and an LLM call, or None."""
    text = f"{item.title} {item.full_text or ''}"
    if SPAM.search(text):
        return "spam"
    if item.metrics.get("xhs_likes", 0) < settings().rednote_min_likes:
        return "low_engagement"
    return None


def gate_batch(items: list[Item]) -> tuple[list[Item], Counter]:
    cfg = settings()
    kept, dropped, per_author, seen = [], Counter(), Counter(), set()
    for it in sorted(items, key=lambda i: -i.metrics.get("xhs_likes", 0)):
        who = it.author_handles.get("rednote") or it.authors[0]
        reason = gate(it)
        fp = _fingerprint(it)
        if not reason and fp in seen:
            reason = "duplicate_text"
        if not reason and per_author[who] >= cfg.rednote_max_per_author:
            reason = "author_cap"
        if reason:
            dropped[reason] += 1
            continue
        seen.add(fp)
        per_author[who] += 1
        kept.append(it)
    return kept, dropped


def _token(item: Item) -> str | None:
    m = re.search(r"xsec_token=([^&]+)", item.media.get("link", ""))
    return m.group(1) if m else None


class RedNoteClient:
    """Thin client for xiaohongshu-mcp's REST API."""

    def __init__(self, http: httpx.AsyncClient):
        cfg = settings()
        self.http, self.base = http, cfg.rednote_mcp_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {cfg.rednote_mcp_token}"} if cfg.rednote_mcp_token else {}

    async def _call(self, method: str, path: str, **kw) -> dict:
        # A search or detail opens a real browser page: allow time for it.
        r = await self.http.request(method, f"{self.base}{path}", headers=self.headers, timeout=90, **kw)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code >= 400 or not body.get("success", False):
            raise RuntimeError(f"{path}: HTTP {r.status_code} {body.get('code', '')} {body.get('error', '')}".strip())
        return body.get("data") or {}

    async def logged_in(self) -> bool:
        return bool((await self._call("GET", "/api/v1/login/status")).get("is_logged_in"))

    async def search(self, keyword: str, filters: dict | None = None) -> list[dict]:
        try:
            data = await self._call("POST", "/api/v1/feeds/search",
                                    json={"keyword": keyword, "filters": filters or {}})
        except RuntimeError as e:
            if "SEARCH_FEEDS_FAILED" in str(e) and any(w in str(e).lower() for w in ("no feeds", "没有")):
                return []  # the server reports an empty result as an error
            raise
        return data.get("feeds") or []

    async def detail(self, feed_id: str, xsec_token: str) -> dict:
        data = await self._call("POST", "/api/v1/feeds/detail", json={"feed_id": feed_id, "xsec_token": xsec_token})
        return ((data.get("data") or {}).get("note")) or {}


@register
class RedNoteConnector(Connector):
    name = "rednote"
    kinds = ("rednote_query",)
    needs = ("rednote_enabled",)

    async def fetch_many(self, http, sources, since) -> FetchResult:
        cfg = settings()
        client = RedNoteClient(http)
        out = FetchResult()
        if not await client.logged_in():
            raise RuntimeError("xiaohongshu-mcp is not logged in to RedNote: run its login (QR scan) first")

        # Searches return about a week of notes and each note is handled once (cursor), so keep the whole week.
        since = min(since, datetime.now(UTC) - timedelta(days=7))
        filters = {"sort_by": cfg.rednote_sort, "publish_time": cfg.rednote_publish_time}
        cards: dict[str, Item] = {}
        owner: dict[str, int] = {}  # note url -> the source that found it first
        seen_by: dict[int, list[str]] = {}
        for s in sources:
            seen = list((s["cursor"] or {}).get("seen", []))
            seen_by[s["id"]] = seen
            try:
                feeds = await client.search(s["value"], filters)
            except Exception as e:
                msg = f"rednote_query:{s['value']}: {e!r}"[:300]
                out.errors.append(msg)
                out.failed[s["id"]] = msg
                continue
            for f in feeds:
                if (it := card_item(f, s["value"])) and f["id"] not in seen and it.url not in cards:
                    cards[it.url] = it
                    owner[it.url] = s["id"]
            log.info("rednote.search", query=s["value"], cards=len(feeds))

        out.seen = len(cards)
        passed, out.dropped = gate_batch(list(cards.values()))
        for it in passed[: cfg.rednote_max_details]:
            note_id = it.url.rsplit("/", 1)[-1]
            if token := _token(it):
                try:
                    note = await client.detail(note_id, token)
                    it = with_detail(it, note) if note else it
                except Exception as e:  # keep the card: the judge still sees title + poster
                    log.warning("rednote.detail_failed", note=note_id, error=repr(e)[:200])
            if it.published_at and it.published_at < since:
                out.dropped["too_old"] += 1
                continue
            out.items.append(it)
        out.dropped["detail_cap"] += max(0, len(passed) - cfg.rednote_max_details)
        out.dropped = Counter({k: v for k, v in out.dropped.items() if v})

        # remember everything handled except notes skipped by the detail cap (they get another chance)
        skipped = {i.url for i in passed[cfg.rednote_max_details:]}
        for url, sid in owner.items():
            if url not in skipped:
                seen_by[sid].append(url.rsplit("/", 1)[-1])
        for s in sources:
            if s["id"] not in out.failed:
                out.states[s["id"]] = {**(s["cursor"] or {}), "seen": seen_by[s["id"]][-SEEN_KEEP:],
                                       "last_scan": datetime.now(UTC).isoformat()}
        log.info("rednote.gate", seen=out.seen, kept=len(out.items), dropped=dict(out.dropped))
        return out
