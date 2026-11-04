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
async def test_x_account_is_incremental_and_caches_user_id():
    lookup = respx.get("https://api.x.com/2/users/by/username/physical_int").mock(
        return_value=httpx.Response(200, json={"data": {"id": "1414", "username": "physical_int"}}))
    timeline = respx.get("https://api.x.com/2/users/1414/tweets").mock(
        return_value=httpx.Response(200, text=fixture("x_v2_user_tweets_synthetic.json")))
    state: dict = {}
    async with http_client() as http:
        items = await REGISTRY["x"].fetch(http, "x_account", "@physical_int", OLD, state=state)
        assert [i.url for i in items] == ["https://x.com/physical_int/status/1900000000000000001",
                                          "https://x.com/physical_int/status/1900000000000000002"]
        first = items[0]
        assert first.outlinks == ["https://arxiv.org/abs/2510.00001"]  # media links dropped
        assert "results on 3 robots" in first.summary                    # long-post text used
        assert first.metrics["x_likes"] == 1200 and first.author_handles == {"x": "physical_int"}
        assert state == {"user_id": "1414", "since_id": "1900000000000000002"}
        assert "start_time" in timeline.calls[0].request.url.params

        await REGISTRY["x"].fetch(http, "x_account", "@physical_int", OLD, state=state)
    assert lookup.call_count == 1                                          # user id cached
    assert timeline.calls[1].request.url.params["since_id"] == "1900000000000000002"
    assert timeline.calls[1].request.headers["authorization"] == "Bearer test-token"


@respx.mock
async def test_x_query_restricts_to_link_posts():
    route = respx.get("https://api.x.com/2/tweets/search/recent").mock(
        return_value=httpx.Response(200, text=fixture("x_v2_user_tweets_synthetic.json")))
    async with http_client() as http:
        await REGISTRY["x"].fetch(http, "x_query", "humanoid robot", OLD, state={})
    q = route.calls[0].request.url.params["query"]
    assert q == "(humanoid robot) has:links -is:retweet -is:reply lang:en"


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
