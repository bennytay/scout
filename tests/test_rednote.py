"""RedNote (小红书): parsing xiaohongshu-mcp's shapes, the free gate, the scan, and the full run into search."""
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from scout.config import settings
from scout.connectors import REGISTRY, http_client
from scout.connectors import rednote as rn
from scout.urls import canonicalize, guess_type

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import xhs_stub  # noqa: E402  (the stand-in server: same JSON shapes as xiaohongshu-mcp)

BASE = "http://xhs.test"
NOTES = xhs_stub.load()
BY_TITLE = {n["title"]: n for n in NOTES}


@pytest.fixture(autouse=True)
def rednote_on(monkeypatch):
    monkeypatch.setenv("REDNOTE_MCP_URL", BASE)  # env, not setattr: the database fixture rebuilds settings
    settings.cache_clear()
    yield
    settings.cache_clear()


def _mock_server(notes=NOTES):
    respx.get(f"{BASE}/api/v1/login/status").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"is_logged_in": True}}))
    respx.post(f"{BASE}/api/v1/feeds/search").mock(side_effect=lambda req: httpx.Response(
        200, json=xhs_stub.search_payload(notes, json.loads(req.content)["keyword"])))
    return respx.post(f"{BASE}/api/v1/feeds/detail").mock(side_effect=lambda req: httpx.Response(
        200, json=xhs_stub.detail_payload(notes, json.loads(req.content)["feed_id"])))


# ---------- parsing (pure) ----------

def test_counts_are_display_strings():
    assert [rn.count(v) for v in ("892", "1.2万", "10万+", "3k", "", None, 7, "n/a")] == \
        [892, 12000, 100000, 3000, 0, 0, 7, 0]


def test_note_urls_canonicalise_without_the_viewer_token():
    want = "https://www.xiaohongshu.com/explore/66f1a2b3c4d5e6f7a8b9c0d1"
    for u in ("https://www.xiaohongshu.com/explore/66f1a2b3c4d5e6f7a8b9c0d1?xsec_token=AB1&xsec_source=pc_feed",
              "https://xiaohongshu.com/discovery/item/66f1a2b3c4d5e6f7a8b9c0d1",
              "http://www.xiaohongshu.com/explore/66f1a2b3c4d5e6f7a8b9c0d1/"):
        assert canonicalize(u) == want
    assert guess_type(want) == "post"


def test_card_and_detail_parse_into_an_item():
    n = BY_TITLE["OpenVLA 上手：7B 开源 VLA，LoRA 单卡微调"]
    card = rn.card_item(xhs_stub.feed(n), "VLA 机器人")
    assert card.url == f"https://www.xiaohongshu.com/explore/{n['id']}" and card.source == "rednote"
    assert card.title.startswith("@VLA笔记: OpenVLA") and card.metrics["xhs_likes"] == 892
    assert f"xsec_token={n['xsec_token']}" in card.media["link"]
    assert rn.card_item({"id": "x", "modelType": "hot_query", "noteCard": {}}) is None

    now = datetime(2026, 11, 7, tzinfo=UTC)
    note = xhs_stub.detail_payload(NOTES, n["id"], now_ms=int(now.timestamp() * 1000))["data"]["data"]["note"]
    it = rn.with_detail(card, note)
    assert it.published_at == now - timedelta(hours=n["h"])
    assert "[话题]" not in it.full_text and "#VLA" in it.full_text and "(posted from 浙江)" in it.full_text
    assert set(it.outlinks) == {"https://github.com/openvla/openvla", "https://arxiv.org/abs/2406.09246"}


def test_gate_drops_spam_low_engagement_and_copies():
    items = [rn.card_item(xhs_stub.feed(n), n["q"]) for n in NOTES]
    kept, dropped = rn.gate_batch(items)
    titles = {i.summary for i in kept}
    assert "ROS机器人毕设代做 SLAM导航 仿真包过" not in titles               # spam: coursework for hire
    assert "具身智能 0 基础入门训练营 第3期 报名中" not in titles              # spam: paid course
    assert "今天读了一篇视觉定位论文，有点没看懂" not in titles               # 6 likes
    assert sum(i.summary.startswith("清华RDT-1B") for i in kept) == 1          # the copy is dropped, original kept
    assert next(i for i in kept if i.summary.startswith("清华RDT-1B")).authors == ["具身小站"]
    assert dropped == {"spam": 2, "low_engagement": 1, "duplicate_text": 1}
    assert "扫地机器人怎么选？双十一闭眼入这3款" in titles                      # free gate passes it; the judge won't


# ---------- the scan ----------

def _sources():
    qs = sorted({n["q"] for n in NOTES})
    return [{"id": i, "kind": "rednote_query", "value": q, "cursor": {}, "config": {}} for i, q in enumerate(qs, 1)]


@respx.mock
async def test_scan_opens_only_gated_notes_and_remembers_them():
    detail = _mock_server()
    since = datetime.now(UTC) - timedelta(days=7)
    async with http_client() as http:
        res = await REGISTRY["rednote"].fetch_many(http, _sources(), since)
    assert not res.errors and res.seen == len(NOTES)
    assert len(res.items) == 10 and detail.call_count == 10  # only cards that passed the free gate are opened
    assert all(i.published_at and i.full_text for i in res.items)
    assert sum(len(s["seen"]) for s in res.states.values()) == len(NOTES)

    sources = [{**s, "cursor": res.states[s["id"]]} for s in _sources()]
    async with http_client() as http:  # next scan: nothing new, nothing opened again
        again = await REGISTRY["rednote"].fetch_many(http, sources, since)
    assert again.seen == 0 and detail.call_count == 10


@respx.mock
async def test_detail_cap_and_logged_out_server(monkeypatch):
    _mock_server()
    monkeypatch.setattr(settings(), "rednote_max_details", 4)
    async with http_client() as http:
        res = await REGISTRY["rednote"].fetch_many(http, _sources(), datetime.now(UTC) - timedelta(days=7))
    assert len(res.items) == 4 and res.dropped["detail_cap"] == 6
    assert sum(len(s["seen"]) for s in res.states.values()) == len(NOTES) - 6  # capped ones get another chance

    respx.get(f"{BASE}/api/v1/login/status").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"is_logged_in": False}}))
    async with http_client() as http:
        with pytest.raises(RuntimeError, match="not logged in"):
            await REGISTRY["rednote"].fetch_many(http, _sources(), datetime.now(UTC))


# ---------- full run: scan -> gate -> judge -> store -> search ----------

async def test_run_rednote_end_to_end(database):
    from scout import search
    from scout.pipeline.run import run_connector

    with respx.mock:
        _mock_server()
        respx.route().mock(return_value=httpx.Response(404))  # outlinks (arXiv, GitHub): fail soft
        stats = await run_connector("rednote")
    assert not stats.errors
    assert stats.fetched == len(NOTES) and stats.gated == 4 and stats.dropped == 2 and stats.inserted == 8
    assert stats.fetched == stats.gated + stats.dropped + stats.inserted + stats.duplicates + stats.failed

    rows = await database.fetch("select title, outlinks, published_at, media from items where source = 'rednote'")
    assert len(rows) == 8 and all(r["published_at"] for r in rows)
    rdt = next(r for r in rows if "RDT-1B" in r["title"])
    assert "https://arxiv.org/abs/2410.07864" in rdt["outlinks"] and "xsec_token" in rdt["media"]["link"]

    # Chinese poster names stay distinct authors (they used to normalise to one empty name)
    assert (await database.fetchrow("select count(*) as n from authors"))["n"] == 8

    found = await search.search(source="rednote", limit=20)
    assert len(found) == 8 and all(f["source"] == "rednote" for f in found)
    assert not any("扫地机器人" in f["title"] for f in found)  # judged promo, never stored
    assert (await search.search(query="MASt3R", source="rednote"))[0]["title"].startswith("@SLAM搬砖人")
    run = await database.fetchrow("select status, fetched from ingest_runs where connector = 'rednote'")
    assert run["status"] == "ok" and run["fetched"] == len(NOTES)


async def test_unconfigured_rednote_is_skipped(database, monkeypatch):
    from scout.pipeline.run import run_connector

    monkeypatch.setattr(settings(), "rednote_mcp_url", None)
    stats = await run_connector("rednote")
    assert stats.fetched == 0 and not stats.errors


async def test_foreign_posts_get_an_english_title_and_embedding(database, monkeypatch):
    """With a real LLM, title_en replaces the Chinese headline; the original stays in full_text."""
    from scout.models import Enrichment, Entities, Item, ItemType
    from scout.pipeline import run as run_mod

    async def fake_enrich(llm, item):
        return Enrichment(summary="Tsinghua's RDT-1B is a 1.2B diffusion model for bimanual manipulation.",
                          title_en="Tsinghua's RDT-1B: a 1.2B-parameter diffusion model for bimanual robots",
                          topics=["manipulation"], authors=[], orgs=["Tsinghua University"], entities=Entities(),
                          importance=0.7, auki_relevance=0.3, auki_relevance_reason="-", signal="news"), 0.0

    monkeypatch.setattr(run_mod, "enrich", fake_enrich)
    item = Item(url="https://www.xiaohongshu.com/explore/0123456789abcdef01234567", type=ItemType.post,
                title="@具身小站: 清华RDT-1B：12亿参数的双臂操作扩散大模型", source="rednote",
                summary="清华 RDT-1B", full_text="清华 RDT-1B 双臂")
    r = await run_mod.Pipeline().process(item)
    row = await database.fetchrow("select title, full_text, embedding is not null as emb from items where id = %s",
                                  r.item_id)
    assert row["title"] == "@具身小站: Tsinghua's RDT-1B: a 1.2B-parameter diffusion model for bimanual robots"
    assert "清华RDT-1B：12亿参数" in row["full_text"] and row["emb"]


# ---------- Discord: /scan_rednote ----------

class _Resp:
    def __init__(self, sent):
        self.sent = sent

    async def defer(self, **kw):
        self.sent.append(("defer", kw))

    async def send_message(self, content=None, **kw):
        self.sent.append(("message", content, kw))


class _Followup:
    def __init__(self, sent):
        self.sent = sent

    async def send(self, content=None, embeds=None, **kw):
        self.sent.append(("followup", content, embeds or []))


class _Interaction:
    """Just enough of discord.Interaction to call a slash command's callback."""

    def __init__(self, client):
        self.client, self.sent = client, []
        self.response, self.followup = _Resp(self.sent), _Followup(self.sent)


def _command(bot, name):
    return next(c for c in bot.tree.get_commands() if c.name == name)


async def test_scan_rednote_command_posts_the_new_notes(database):
    from scout.bot.main import ScoutBot

    bot = ScoutBot()
    cmd = _command(bot, "scan_rednote")
    assert "RedNote" in cmd.description

    with respx.mock:
        _mock_server()
        respx.route().mock(return_value=httpx.Response(404))
        ia = _Interaction(bot)
        await cmd.callback(ia)
    assert ia.sent[0][0] == "defer"
    first = ia.sent[1]
    assert first[0] == "followup" and "14 notes found → 10 passed the filter → **8 new** kept" in first[1]
    assert "2 judged out" in first[1]
    cards = [e.to_dict() for msg in ia.sent[1:] for e in msg[2]]
    assert len(cards) == 8
    top = cards[0]  # most important first; each card leads with the English headline and links the note
    assert "xsec_token=" in top["url"] and top["author"]["name"].startswith("小红书 RedNote · ")
    assert "❤" in top["footer"]["text"] and "importance" in top["footer"]["text"]
    rdt = next(c for c in cards if "RDT" in c["title"])
    assert "[arXiv 2410.07864](https://arxiv.org/abs/2410.07864)" in rdt["description"]

    with respx.mock:  # again: every note was already read, so nothing new
        _mock_server()
        ia = _Interaction(bot)
        await cmd.callback(ia)
    assert "**0 new**" in ia.sent[1][1] and "Nothing new since the last scan" in ia.sent[1][1]


async def test_scan_rednote_command_reports_failures_and_missing_setup(database, monkeypatch):
    from scout.bot.main import ScoutBot

    bot = ScoutBot()
    cmd = _command(bot, "scan_rednote")
    with respx.mock:  # server up but logged out
        respx.get(f"{BASE}/api/v1/login/status").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"is_logged_in": False}}))
        ia = _Interaction(bot)
        await cmd.callback(ia)
    assert ia.sent[-1][0] == "followup" and "RedNote scan failed" in ia.sent[-1][1] and "not logged in" in ia.sent[-1][1]

    monkeypatch.setattr(bot.cfg, "rednote_mcp_url", None)
    ia = _Interaction(bot)
    await cmd.callback(ia)
    assert ia.sent == [("message", ia.sent[0][1], {"ephemeral": True})] and "REDNOTE_MCP_URL" in ia.sent[0][1]
