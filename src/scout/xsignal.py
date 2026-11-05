"""High-signal X: the free rule gate that runs before any LLM sees a post.

The funnel (see README):
  1. radar      curated accounts. Trusted: they skip the reputation rules and go straight to the judge.
  2. discovery  posts from anyone that link to research (arXiv, GitHub, Hugging Face, project pages), plus a
                general-news search (launches, funding, deployments) held to a higher engagement bar.
  3. gate       (this module) spam lexicon, research link, engagement, reputation, per-author cap, duplicates.
  4. judge      the enrichment call labels each post news | discussion | promo | off_topic | noise.
  5. expand     kept posts pull in the paper / repo / model they link to.
  6. learn      per-account hit rate; good non-radar accounts get suggested for the radar.

Everything here is pure and unit-tested; thresholds live in config.
"""
import hashlib
import re
from collections import Counter
from datetime import datetime

from .config import settings
from .models import Item

RESEARCH = re.compile(
    r"https?://([\w-]+\.)*(arxiv\.org|github\.com|github\.io|huggingface\.co|openreview\.net|alphaxiv\.org|"
    r"paperswithcode\.com)(/|$)", re.I)
SPAM = re.compile(
    r"airdrop|giveaway|presale|whitelist|memecoin|\bnfts?\b|\bsolana\b|\bcrypto\b|to the moon|link in bio|"
    r"\bdm me\b|use (my )?code|% off\b|limited spots|join (my|our) (discord|telegram)|\bpromo\b", re.I)
TICKER = re.compile(r"(?<!\w)\$[A-Z]{2,6}\b")
DROP_SIGNALS = {"promo", "off_topic", "noise"}  # judge labels that are never stored


def handle(item: Item) -> str:
    return (item.author_handles.get("x") or "").lower()


def has_research_link(item: Item) -> bool:
    return any(RESEARCH.match(u) for u in item.outlinks)


def gate(item: Item, on_radar: bool, now: datetime) -> str | None:
    """Return why a post should be dropped, or None to pass it to the judge."""
    if on_radar:
        return None
    cfg = settings()
    text = item.full_text or item.summary or ""
    if SPAM.search(text) or TICKER.search(text):
        return "spam"
    likes = item.metrics.get("x_likes", 0)
    if item.source_ref == "news":  # general-news discovery: no research link, so a higher bar instead
        if likes < cfg.x_news_min_likes:
            return "low_engagement"
        if (item.metrics.get("x_followers", 0) < cfg.x_news_min_followers
                or item.metrics.get("x_account_age_days", 0) < cfg.x_min_account_age_days):
            return "low_reputation"
        return None
    if not has_research_link(item):
        return "no_research_link"
    if likes < cfg.x_min_likes:
        return "low_engagement"
    if likes < cfg.x_viral_likes and (item.metrics.get("x_followers", 0) < cfg.x_min_followers
                                      or item.metrics.get("x_account_age_days", 0) < cfg.x_min_account_age_days):
        return "low_reputation"
    return None


def _fingerprint(item: Item) -> str:
    words = re.findall(r"[a-z0-9]+", re.sub(r"https?://\S+", "", (item.full_text or item.title).lower()))
    return hashlib.md5(" ".join(words[:40]).encode()).hexdigest()


def gate_batch(items: list[Item], radar: set[str], now: datetime) -> tuple[list[Item], Counter]:
    """Gate a scan's posts. Also caps posts per author and drops copy-paste duplicates."""
    cfg = settings()
    kept, dropped, per_author, seen = [], Counter(), Counter(), set()
    # most-liked first, so the per-author cap keeps each account's best posts
    for it in sorted(items, key=lambda i: -i.metrics.get("x_likes", 0)):
        h = handle(it)
        on_radar = h in radar
        reason = gate(it, on_radar, now)
        fp = _fingerprint(it)
        if not reason and fp in seen:
            reason = "duplicate_text"
        if not reason and per_author[h] >= (cfg.x_max_per_radar_author if on_radar else cfg.x_max_per_author):
            reason = "author_cap"
        if reason:
            dropped[reason] += 1
            continue
        seen.add(fp)
        per_author[h] += 1
        kept.append(it)
    return kept, dropped


def batch_queries(handles: list[str], suffix: str, limit: int = 512) -> list[list[str]]:
    """Pack handles into `(from:a OR from:b …) <suffix>` queries under the API's query-length limit."""
    batches: list[list[str]] = []
    cur: list[str] = []
    for h in handles:
        trial = cur + [h]
        if cur and len(radar_query(trial, suffix)) > limit:
            batches.append(cur)
            cur = [h]
        else:
            cur = trial
    if cur:
        batches.append(cur)
    return batches


def radar_query(handles: list[str], suffix: str) -> str:
    return "(" + " OR ".join(f"from:{h}" for h in handles) + ") " + suffix
