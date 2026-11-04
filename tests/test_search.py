"""Hybrid search behaviour: lexical, fuzzy author/org, filters, feedback boost, related items."""
from datetime import UTC, datetime, timedelta

from scout import search
from scout.models import Item, ItemType
from scout.pipeline.run import Pipeline

NOW = datetime.now(UTC)
CORPUS = [
    ("https://arxiv.org/abs/2510.10001", "paper", "Collaborative visual relocalization across robot fleets",
     "Robots share a spatial map and relocalize against each other.", ["Sergey Levine"], ["UC Berkeley"], 1),
    ("https://arxiv.org/abs/2510.10002", "paper", "A vision-language-action model for dexterous manipulation",
     "A VLA foundation model that grasps unseen objects.", ["Chelsea Finn"], ["Stanford University"], 2),
    ("https://arxiv.org/abs/2510.10003", "paper", "Legged locomotion over rough terrain with reinforcement learning",
     "Quadruped gait learned in simulation and transferred sim2real.", ["Marco Hutter"], ["ETH Zurich"], 40),
    ("https://github.com/lab/humanoid-wbc", "repo", "lab/humanoid-wbc: whole-body control for humanoid robots",
     "Open-source humanoid controller.", ["Jim Fan"], ["NVIDIA"], 3),
    ("https://example.com/unitree-news", "article", "Unitree ships a cheaper humanoid",
     "Industry news about humanoid pricing.", [], ["Unitree"], 5),
]


async def seed():
    p = Pipeline()
    ids = []
    for url, typ, title, summary, authors, orgs, age in CORPUS:
        r = await p.process(Item(url=url, type=ItemType(typ), title=title, summary=summary, source="test",
                                 authors=authors, orgs=orgs, published_at=NOW - timedelta(days=age)))
        ids.append(r.item_id)
    return ids


async def test_keyword_search_ranks_the_obvious_hit_first(database):
    ids = await seed()
    r = await search.search("visual relocalization")
    assert r[0]["id"] == ids[0] and r[0]["url"] and "fts:1" in r[0]["matched"]


async def test_fuzzy_author_and_org_filters(database):
    ids = await seed()
    assert [x["id"] for x in await search.search(author="levine")] == [ids[0]]
    assert [x["id"] for x in await search.search(author="Chelsea Fin")] == [ids[1]]  # typo-tolerant
    assert [x["id"] for x in await search.search(org="eth zürich")] == [ids[2]]
    assert [x["id"] for x in await search.search(org="nvidia")] == [ids[3]]


async def test_query_matching_an_author_name_finds_their_work(database):
    ids = await seed()
    r = await search.search("Marco Hutter")
    assert r[0]["id"] == ids[2] and any(m.startswith("fuzzy") for m in r[0]["matched"])


async def test_topic_type_and_since_filters(database):
    ids = await seed()
    humanoid = {x["id"] for x in await search.search(topic="humanoids")}
    assert humanoid == {ids[3], ids[4]}
    assert {x["id"] for x in await search.search(topic="humanoids", type="repo")} == {ids[3]}
    recent = {x["id"] for x in await search.search(since="7d")}
    assert ids[2] not in recent and ids[0] in recent


async def test_related_author_profile_trending(database):
    ids = await seed()
    rel = await search.find_related(ids[0])
    assert rel and all("url" in r for r in rel)
    prof = await search.author_profile("levine")
    assert prof["name"] == "Sergey Levine" and prof["recent_items"][0]["id"] == ids[0]
    tr = await search.trending(days=10)
    assert ids[2] not in [t["id"] for t in tr]  # 40 days old
    d = await search.digest(7)
    assert d["stats"]["items"] == 5


async def test_ask_cites_sources(database):
    await seed()
    r = await search.ask("relocalization across robot fleets")
    assert r["sources"] and r["sources"][0]["url"].startswith("https://")


async def test_min_relevance_filter(database):
    await seed()
    rows = await search.search(min_relevance=0.7)
    assert rows and all(r["auki_relevance"] >= 0.7 for r in rows)
    assert await search.search("humanoid", min_relevance=0.99) == []
