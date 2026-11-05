"""Connector parsing against recorded real responses (tests/fixtures). No network."""
from datetime import UTC, datetime

import httpx
import respx
from conftest import fixture

from scout.connectors import REGISTRY, http_client
from scout.connectors.resolve import resolve
from scout.urls import canonicalize

OLD = datetime(2000, 1, 1, tzinfo=UTC)


@respx.mock
async def test_arxiv():
    respx.get(url__startswith="https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=fixture("arxiv_cs_ro.xml")))
    async with http_client() as http:
        items = await REGISTRY["arxiv"].fetch(http, "arxiv_category", "cs.RO", OLD)
    assert len(items) == 5
    i = items[0]
    assert i.type == "paper" and i.arxiv_id and i.url == f"https://arxiv.org/abs/{i.arxiv_id}"
    assert i.authors and i.summary and i.published_at


@respx.mock
async def test_hackernews():
    respx.get(url__startswith="https://hn.algolia.com").mock(return_value=httpx.Response(200, text=fixture("hn_robot.json")))
    async with http_client() as http:
        items = await REGISTRY["hackernews"].fetch(http, "hn_query", "robot", OLD)
    assert len(items) == 5
    assert all("hn_points" in i.metrics for i in items)


@respx.mock
async def test_alphaxiv_filters_to_robotics_and_arxiv():
    respx.get(url__startswith="https://api.alphaxiv.org").mock(
        return_value=httpx.Response(200, text=fixture("alphaxiv_hot.json")))
    async with http_client() as http:
        items = await REGISTRY["alphaxiv"].fetch(http, "alphaxiv", "robotics", OLD)
    assert all(i.arxiv_id and i.url.startswith("https://arxiv.org/abs/") for i in items)
    assert len(items) < 30  # non-robotics papers dropped


@respx.mock
async def test_alphaxiv_fails_soft():
    respx.get(url__startswith="https://api.alphaxiv.org").mock(return_value=httpx.Response(503))
    async with http_client() as http:
        assert await REGISTRY["alphaxiv"].fetch(http, "alphaxiv", "robotics", OLD) == []


@respx.mock
async def test_hf_daily_papers():
    respx.get(url__startswith="https://huggingface.co/api/daily_papers").mock(
        return_value=httpx.Response(200, text=fixture("hf_daily.json")))
    async with http_client() as http:
        items = await REGISTRY["huggingface"].fetch(http, "hf_feed", "daily_papers", datetime.now(UTC))
    assert len(items) == 5 and all(i.arxiv_id and "hf_upvotes" in i.metrics for i in items)


@respx.mock
async def test_rss():
    respx.get("https://www.therobotreport.com/feed/").mock(
        return_value=httpx.Response(200, content=fixture("rss_robotreport.xml").encode()))
    async with http_client() as http:
        items = await REGISTRY["rss"].fetch(http, "rss", "https://www.therobotreport.com/feed/", OLD)
    assert len(items) == 15 and all(i.title and i.url.startswith("http") for i in items)


@respx.mock
async def test_resolve_x_link_without_api_key():
    respx.get("https://api.fxtwitter.com/status/20").mock(
        return_value=httpx.Response(200, text=fixture("fxtwitter_status.json")))
    async with http_client() as http:
        item = await resolve(http, "https://twitter.com/jack/status/20?s=20")
    assert canonicalize(item.url) == "https://x.com/jack/status/20" and item.type == "post"
    assert item.metrics["x_likes"] > 0 and item.source == "discord"


@respx.mock
async def test_resolve_github_repo():
    respx.get("https://api.github.com/repos/huggingface/lerobot").mock(
        return_value=httpx.Response(200, text=fixture("gh_repo.json")))
    respx.get("https://api.github.com/repos/huggingface/lerobot/readme").mock(
        return_value=httpx.Response(200, text="# LeRobot\nSee https://arxiv.org/abs/2602.22818 and our docs."))
    async with http_client() as http:
        item = await resolve(http, "https://github.com/huggingface/lerobot/tree/main")
    assert item.type == "repo" and item.metrics["gh_stars"] > 1000
    assert "https://arxiv.org/abs/2602.22818" in item.outlinks


def test_post_title_is_readable():
    from scout.connectors.x import post_title

    t = post_title("🚨 BREAKING:\n\nFigure's humanoid folds laundry for 8 hours straight https://t.co/x", "someone")
    assert t == "@someone: 🚨 BREAKING: Figure's humanoid folds laundry for 8 hours straight"
    assert post_title("word " * 60, "a").endswith("…") and len(post_title("word " * 60, "a")) < 140


def test_hf_owner_is_a_handle_not_an_org():
    from scout.connectors.huggingface import hub_item

    i = hub_item({"id": "lyl472324464/so100_pick", "likes": 3}, "datasets")
    assert i.orgs == [] and i.author_handles == {"hf": "lyl472324464"}


@respx.mock
async def test_github_lean_mode_without_token():
    import json as _json

    repos = [_json.loads(fixture("gh_repo.json")) | {"full_name": f"org/r{i}", "html_url": f"https://github.com/org/r{i}",
             "created_at": "2026-11-01T00:00:00Z", "pushed_at": "2026-11-03T00:00:00Z", "fork": False, "archived": False}
             for i in range(6)]
    respx.get("https://api.github.com/orgs/org/repos").mock(return_value=httpx.Response(200, json=repos))
    readme = respx.get(url__regex=r".*/readme$").mock(return_value=httpx.Response(200, text="# hi"))
    rel = respx.get(url__regex=r".*/releases(\?.*)?$").mock(return_value=httpx.Response(200, json=[]))
    async with http_client() as http:
        items = await REGISTRY["github"].fetch(http, "github_org", "org", OLD)
    assert len(items) == 6 and readme.call_count == 0 and rel.call_count == 2  # ~3 calls, not ~13
