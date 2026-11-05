"""X: the signal gate (pure), the batched scan (recorded real responses), and the full run with judge + expand."""
import json
from datetime import UTC, datetime, timedelta

import httpx
import respx
from conftest import fixture

from scout import xsignal
from scout.connectors import REGISTRY, http_client
from scout.connectors import x as xconn
from scout.models import Item, ItemType

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
SEARCH = "https://api.x.com/2/tweets/search/recent"


def post(handle="someone", text="New paper on humanoid control", likes=100, followers=5000, age=1000,
         links=("https://arxiv.org/abs/2611.00001",)) -> Item:
    return Item(url=f"https://x.com/{handle}/status/{abs(hash((handle, text))) % 10**9}", type=ItemType.post,
                title=text[:60], source="x", full_text=text, summary=text, author_handles={"x": handle},
                metrics={"x_likes": likes, "x_followers": followers, "x_account_age_days": age},
                outlinks=list(links))


# ---------- gate (pure) ----------

def test_radar_accounts_skip_the_gate():
    p = post(likes=0, followers=0, age=1, links=())
    assert xsignal.gate(p, on_radar=True, now=NOW) is None


def test_discovery_needs_a_research_link():
    assert xsignal.gate(post(links=("https://example.com/blog",)), False, NOW) == "no_research_link"
    for link in ("https://github.com/a/b", "https://foo.github.io/project", "https://huggingface.co/x/y"):
        assert xsignal.gate(post(links=(link,)), False, NOW) is None


def test_spam_and_tickers_are_dropped():
    assert xsignal.gate(post(text="Solana robotics airdrop, link in bio"), False, NOW) == "spam"
    assert xsignal.gate(post(text="Robots will 100x $ROBO holders"), False, NOW) == "spam"
    assert xsignal.gate(post(text="Our policy runs 10x faster on the G1 humanoid"), False, NOW) is None


def test_engagement_and_reputation():
    assert xsignal.gate(post(likes=3), False, NOW) == "low_engagement"
    assert xsignal.gate(post(likes=20, followers=20), False, NOW) == "low_reputation"
    assert xsignal.gate(post(likes=20, age=10), False, NOW) == "low_reputation"
    assert xsignal.gate(post(likes=224, followers=157), False, NOW) is None  # viral beats reputation


def test_batch_caps_authors_and_drops_copies():
    posts = [post("spammy", f"Paper {i} on robot grasping", likes=20 + i) for i in range(5)]
    posts += [post("a", "Same text robot grasping"), post("b", "Same text robot grasping")]
    kept, dropped = xsignal.gate_batch(posts, radar=set(), now=NOW)
    assert sum(1 for p in kept if p.author_handles["x"] == "spammy") == 3
    assert dropped == {"author_cap": 2, "duplicate_text": 1}
    # the cap keeps each author's most-liked posts
    assert {p.metrics["x_likes"] for p in kept if p.author_handles["x"] == "spammy"} == {22, 23, 24}


def test_batch_queries_fit_the_limit_and_keep_every_handle():
    handles = [f"handle_{i:03d}" for i in range(80)]
    batches = xsignal.batch_queries(handles, xconn.RADAR_SUFFIX, 512)
    assert [h for b in batches for h in b] == handles
    assert all(len(xsignal.radar_query(b, xconn.RADAR_SUFFIX)) <= 512 for b in batches)
    assert len(batches) <= 5


def test_follow_targets_pick_research_links():
    from scout.pipeline.run import follow_targets

    p = post(links=("https://example.com/news", "https://arxiv.org/abs/2611.00001v2", "https://foo.github.io/proj",
                    "https://github.com/a/b", "https://huggingface.co/x/y"))
    assert follow_targets(p) == ["https://arxiv.org/abs/2611.00001", "https://foo.github.io/proj", "https://github.com/a/b"]


# ---------- scan against recorded real responses ----------

def _route():
    def reply(request):
        q = request.url.params["query"]
        return httpx.Response(200, text=fixture("x_search_radar.json" if "from:" in q else "x_search_discovery.json"))
    return respx.get(SEARCH).mock(side_effect=reply)


@respx.mock
async def test_scan_batches_radar_and_delays_discovery():
    route = _route()
    radar = json.loads(fixture("x_search_radar.json"))
    handles = sorted({u["username"] for u in radar["includes"]["users"]})
    sources = [{"id": i, "kind": "x_account", "value": h, "cursor": {}} for i, h in enumerate(handles)]
    sources.append({"id": 99, "kind": "x_query", "value": "url:arxiv.org robot", "cursor": {}})
    since = datetime.now(UTC) - timedelta(days=2)
    async with http_client() as http:
        res = await REGISTRY["x"].fetch_many(http, sources, since)

    assert route.call_count == 2  # one radar batch + one discovery query
    radar_q = route.calls[0].request.url.params
    assert radar_q["query"].startswith("(from:") and radar_q["query"].endswith("-is:retweet -is:reply")
    disc = route.calls[1].request.url.params
    assert disc["query"] == "(url:arxiv.org robot) -is:retweet -is:reply lang:en"
    disc_end = datetime.fromisoformat(disc["end_time"].replace("Z", "+00:00"))
    assert disc_end <= datetime.now(UTC) - timedelta(hours=5, minutes=59)  # likes have had time to accrue
    assert set(res.states) == {s["id"] for s in sources} and all("until" in st for st in res.states.values())

    assert res.seen == 62 and res.seen == len(res.items) + sum(res.dropped.values())
    kept = {i.author_handles["x"] for i in res.items}
    assert set(handles) <= kept                                    # radar is trusted
    assert "danielpmorton" in kept                                  # 224 likes, research link
    assert not kept & {"SanemBuilds", "mengpaper", "elessarqq"}     # 0-follower bots, engagement bait
    assert res.dropped["low_engagement"] > 20                       # most of discovery is noise
    first = next(i for i in res.items if i.author_handles["x"] == "danielpmorton")
    assert first.metrics["x_followers"] == 157 and first.metrics["x_account_age_days"] > 0
    assert any(u.startswith("https://") and "t.co" not in u for u in first.outlinks)


@respx.mock
async def test_scan_resumes_from_cursor():
    route = _route()
    until = (datetime.now(UTC) - timedelta(hours=1)).replace(microsecond=0)
    sources = [{"id": 1, "kind": "x_account", "value": "svlevine", "cursor": {"until": until.isoformat()}}]
    async with http_client() as http:
        await REGISTRY["x"].fetch_many(http, sources, datetime.now(UTC) - timedelta(days=2))
    assert route.calls[0].request.url.params["start_time"] == until.strftime("%Y-%m-%dT%H:%M:%SZ")


@respx.mock
async def test_consumer_key_is_exchanged_for_a_bearer_token(monkeypatch):
    from scout.config import settings

    monkeypatch.setattr(settings(), "x_bearer_token", None)
    monkeypatch.setattr(settings(), "x_api_key", "key")
    monkeypatch.setattr(settings(), "x_api_secret", "secret")
    monkeypatch.setattr(xconn, "_bearer", None)
    token = respx.post("https://api.x.com/oauth2/token").mock(
        return_value=httpx.Response(200, json={"token_type": "bearer", "access_token": "app-token"}))
    route = _route()
    sources = [{"id": 1, "kind": "x_account", "value": "svlevine", "cursor": {}}]
    async with http_client() as http:
        for _ in range(2):
            await REGISTRY["x"].fetch_many(http, sources, datetime.now(UTC) - timedelta(days=1))
    assert token.call_count == 1  # cached
    assert route.calls[0].request.headers["authorization"] == "Bearer app-token"
    assert settings().x_enabled


async def _val(database, sql):
    return list((await database.fetchrow(sql)).values())[0]


# ---------- full run: gate -> judge -> store -> expand -> learn ----------

async def test_run_x_gates_judges_expands_and_learns(database):
    from scout.pipeline.run import run_connector

    await database.execute("update sources set enabled = false where kind = 'x_query' and value not like '%%arxiv%%'")
    with respx.mock:
        _route()
        respx.get(url__startswith="https://export.arxiv.org").mock(
            return_value=httpx.Response(200, text=fixture("arxiv_cs_ro.xml")))
        respx.route().mock(return_value=httpx.Response(404))  # other outlinks: fail soft
        stats = await run_connector("x")
    assert not stats.errors
    assert stats.fetched == 62 and stats.inserted > 0 and stats.dropped > 30
    posts = await _val(database, "select count(*) from items where type = 'post'")
    assert 0 < posts <= stats.inserted
    # expand: kept posts pulled in the papers they link to (the mock serves one canned arXiv paper)
    assert await _val(database, "select count(*) from items where type = 'paper'") > 0
    # learn: per-account judge results recorded
    assert await _val(database, "select sum(judged) from x_accounts") > 0
    run = await database.fetchrow("select fetched, dropped from ingest_runs where connector = 'x'")
    assert run["fetched"] == 62 and run["dropped"] == stats.dropped
    radar = await database.fetchrow("select cursor from sources where kind = 'x_account' and value = 'svlevine'")
    assert "until" in radar["cursor"]

    with respx.mock:  # API down: sources marked failing, the run still completes
        respx.route().mock(return_value=httpx.Response(503))
        stats = await run_connector("x")
    assert stats.errors
    src = await database.fetchrow("select consecutive_failures from sources where value = 'svlevine'")
    assert src["consecutive_failures"] == 1
