"""Pipeline against a real Postgres (pgvector): dedupe ladder, sightings/metrics merge, linking."""
from datetime import UTC, datetime

from scout.models import Item, ItemType
from scout.pipeline.run import Pipeline

NOW = datetime.now(UTC)


def paper(**kw) -> Item:
    base = {"url": "https://arxiv.org/abs/2510.00001v2", "type": ItemType.paper, "source": "arxiv",
                "title": "Collaborative SLAM for robot fleets with shared spatial maps",
                "summary": "We merge maps from many robots without a central server.", "published_at": NOW,
                "authors": ["Ada Lovelace", "Alan Turing"], "arxiv_id": "2510.00001"}
    return Item(**{**base, **kw})


async def test_exact_dedupe_across_sources_merges_metrics(database):
    p = Pipeline()
    a = await p.process(paper())
    b = await p.process(paper(url="https://huggingface.co/papers/2510.00001", source="huggingface",
                              metrics={"hf_upvotes": 42}, arxiv_id=None))
    c = await p.process(paper(url="https://arxiv.org/pdf/2510.00001v3.pdf", source="hackernews",
                              metrics={"hn_points": 120}, arxiv_id=None))
    assert a.status == "inserted" and b.status == c.status == "duplicate" and a.item_id == b.item_id == c.item_id
    row = await database.fetchrow("select metrics from items where id = %s", a.item_id)
    assert row["metrics"] == {"hf_upvotes": 42, "hn_points": 120}
    seen = await database.fetch("select source from item_sources where item_id = %s order by source", a.item_id)
    assert [r["source"] for r in seen] == ["arxiv", "hackernews", "huggingface"]
    assert (await database.fetchrow("select count(*) as n from items"))["n"] == 1


async def test_reprocessing_is_idempotent(database):
    p = Pipeline()
    for _ in range(3):
        await p.process(paper())
    counts = await database.fetchrow(
        """select (select count(*) from items) as items, (select count(*) from item_authors) as ia,
                  (select count(*) from authors) as authors, (select count(*) from item_topics) as topics""")
    assert counts["items"] == 1 and counts["ia"] == 2 and counts["authors"] == 2 and counts["topics"] >= 1


async def test_semantic_dedupe_only_for_posts_and_articles(database):
    p = Pipeline()
    text = "Figure unveils its new humanoid robot for home use with dexterous hands and a VLA brain"
    a = await p.process(Item(url="https://site-a.com/story", type=ItemType.article, title=text, source="rss"))
    b = await p.process(Item(url="https://site-b.com/news/figure", type=ItemType.article, title=text, source="rss"))
    assert b.status == "duplicate" and b.item_id == a.item_id
    # Same text but different papers with different arXiv ids: must NOT merge.
    c = await p.process(paper(url="https://arxiv.org/abs/2510.00002", arxiv_id="2510.00002"))
    d = await p.process(paper(url="https://arxiv.org/abs/2510.00003", arxiv_id="2510.00003"))
    assert c.status == d.status == "inserted" and c.item_id != d.item_id


async def test_links_resolve_in_either_arrival_order(database):
    p = Pipeline()
    # Repo arrives first and mentions the paper in its README; paper arrives later.
    repo = await p.process(Item(url="https://github.com/lab/fleet-slam", type=ItemType.repo, source="github",
                                title="lab/fleet-slam", full_text="Code for arXiv:2510.00001 (see paper)."))
    pap = await p.process(paper())
    post = await p.process(Item(url="https://x.com/lab/status/1", type=ItemType.post, source="x",
                                title="Our fleet SLAM paper is out", outlinks=["https://arxiv.org/pdf/2510.00001"]))
    links = await database.fetch("select src_item_id, dst_item_id, relation from item_links order by relation")
    assert {(l["src_item_id"], l["dst_item_id"], l["relation"]) for l in links} == {
        (post.item_id, pap.item_id, "discusses"), (repo.item_id, pap.item_id, "implements")}


async def test_cost_is_tracked_per_item(database):
    p = Pipeline()
    r = await p.process(paper())
    row = await database.fetchrow("select cost_usd, enrich_status, enrich_model from items where id = %s", r.item_id)
    assert row["enrich_status"] == "done" and row["enrich_model"] == "fake-heuristic" and row["cost_usd"] == 0


async def test_run_connector_persists_cursor_and_isolates_failures(database):
    import httpx
    import respx
    from conftest import fixture

    from scout.pipeline.run import run_connector

    with respx.mock:
        respx.get("https://api.x.com/2/users/by/username/physical_int").mock(
            return_value=httpx.Response(200, json={"data": {"id": "1414"}}))
        respx.get("https://api.x.com/2/users/1414/tweets").mock(
            return_value=httpx.Response(200, text=fixture("x_v2_user_tweets_synthetic.json")))
        stats = await run_connector("x", only_value="physical_int")
    assert stats.inserted == 2 and not stats.errors
    src = await database.fetchrow("select cursor, consecutive_failures from sources where value = 'physical_int'")
    assert src["cursor"] == {"user_id": "1414", "since_id": "1900000000000000002"}

    with respx.mock:  # API down: the source is marked failing, the run still completes
        respx.get(url__startswith="https://api.x.com/2/").mock(return_value=httpx.Response(503))
        stats = await run_connector("x", only_value="physical_int")
    assert len(stats.errors) == 1
    src = await database.fetchrow("select cursor, consecutive_failures from sources where value = 'physical_int'")
    assert src["consecutive_failures"] == 1 and src["cursor"]["since_id"] == "1900000000000000002"
