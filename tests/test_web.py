"""Web UI: search/facets, item pages, curation that survives re-enrichment, sources, auth."""
import httpx
import pytest

from scout.config import settings
from scout.models import Item, ItemType
from scout.pipeline.run import Pipeline


@pytest.fixture
async def client(database):
    from scout.web.app import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def seed():
    p = Pipeline()
    a = await p.process(Item(url="https://arxiv.org/abs/2510.20001", type=ItemType.paper, source="arxiv",
                             title="Collaborative SLAM for robot fleets", summary="Shared spatial maps across robots.",
                             authors=["Marco Hutter"], orgs=["ETH Zurich"]))
    b = await p.process(Item(url="https://example.com/off-topic", type=ItemType.article, source="rss",
                             title="Quarterly earnings of a bakery", summary="Bread prices."))
    return a.item_id, b.item_id


async def test_search_page_facets_and_off_topic_floor(client, database):
    good, off = await seed()
    await database.execute("update items set auki_relevance = 0.1 where id = %s", off)
    r = await client.get("/")
    assert r.status_code == 200 and "Collaborative SLAM" in r.text and "bakery" not in r.text  # off-topic hidden
    assert "bakery" in (await client.get("/?all=1")).text
    r = await client.get("/?author=hutter&topic=slam-spatial-mapping")
    assert "Collaborative SLAM" in r.text and "author: hutter ✕" in r.text
    assert "Collaborative SLAM" not in (await client.get("/?org=nvidia")).text


async def test_item_author_sources_pages(client, database):
    good, _ = await seed()
    assert "Collaborative SLAM" in (await client.get(f"/item/{good}")).text
    assert (await client.get("/item/999999")).status_code == 200  # friendly not-found
    assert "Marco Hutter" in (await client.get("/authors?q=huter")).text  # typo-tolerant
    assert "Collaborative SLAM" in (await client.get("/author?name=Marco%20Hutter")).text
    r = await client.get("/sources")
    assert r.status_code == 200 and "cs.RO" in r.text


async def test_curation_survives_reenrichment(client, database):
    from scout.pipeline.store import reenrich

    good, _ = await seed()
    r = await client.post(f"/item/{good}/curate", data={"topics": ["hardware"], "relevance": "0.95", "note": "core"})
    assert r.status_code == 303
    await reenrich(good)
    row = await database.fetchrow(
        """select auki_relevance, curated_note, (select array_agg(topic_slug) from item_topics where item_id = i.id) t
           from items i where id = %s""", good)
    assert abs(row["auki_relevance"] - 0.95) < 1e-6 and row["t"] == ["hardware"] and row["curated_note"] == "core"


async def test_delete_and_source_management(client, database):
    good, _ = await seed()
    await client.post(f"/item/{good}/delete")
    assert await database.fetchrow("select 1 from items where id = %s", good) is None
    await client.post("/sources/add", data={"kind": "rss", "value": "https://example.com/feed.xml"})
    src = await database.fetchrow("select id, enabled from sources where value = 'https://example.com/feed.xml'")
    assert src["enabled"]
    await client.post(f"/sources/{src['id']}/toggle")
    assert not (await database.fetchrow("select enabled from sources where id = %s", src["id"]))["enabled"]


async def test_json_api(client, database):
    await seed()
    r = await client.get("/api/search", params={"q": "SLAM fleets", "limit": 5})
    assert r.json()[0]["title"] == "Collaborative SLAM for robot fleets"


async def test_password_when_configured(client, database, monkeypatch):
    monkeypatch.setattr(settings(), "web_password", "pw")
    assert (await client.get("/")).status_code == 401
    assert (await client.get("/", auth=("any", "pw"))).status_code == 200


async def test_brief_page(client, database):
    assert "No brief yet" in (await client.get("/brief")).text
    await database.execute("""insert into briefs (window_start, window_end, n_candidates, n_new_items, model, stories)
        values (now() - interval '1 day', now(), 5, 9, 'fake', '[{"headline": "Big news", "why": "w", "hot": true,
        "links": [{"label": "paper: X", "url": "https://arxiv.org/abs/1", "item_id": 1, "type": "paper"}]}]')""")
    r = await client.get("/brief")
    assert "Big news" in r.text and "paper: X" in r.text
