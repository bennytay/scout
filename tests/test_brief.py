"""Brief: candidate pool (X-first, links), and assembly that can't invent or reuse items."""
from datetime import UTC, datetime, timedelta

from scout.brief import Brief, Story, assemble, candidate_lines, candidates, make_brief
from scout.models import Item, ItemType
from scout.pipeline.run import Pipeline

NOW = datetime.now(UTC)


async def seed():
    p = Pipeline()
    paper = await p.process(Item(url="https://arxiv.org/abs/2511.00001", type=ItemType.paper, source="arxiv",
                                 title="Collaborative SLAM: shared maps for robot fleets", summary="Fleet mapping."))
    post = await p.process(Item(url="https://x.com/lab/status/1", type=ItemType.post, source="x",
                                title="@lab: our fleet SLAM paper is out", summary="Robots share one map.",
                                metrics={"x_likes": 900}, outlinks=["https://arxiv.org/abs/2511.00001"]))
    return paper.item_id, post.item_id


async def test_candidates_put_x_first_and_carry_links(database):
    paper, post = await seed()
    await database.execute("update items set auki_relevance = 0.9")
    pool = await candidates(NOW - timedelta(hours=1), NOW + timedelta(minutes=1))
    assert set(pool) == {paper, post} and pool[post]["links"] == [paper]
    text = candidate_lines(pool)
    assert text.index(f"[{post}] X POST") < text.index(f"[{paper}] PAPER") and "❤900" in text


def test_assemble_drops_invented_and_reused_ids():
    pool = {1: {"rel": 0.9, "url": "https://x.com/a/status/1", "type": "post", "title": "t"},
            2: {"rel": 0.5, "url": "https://arxiv.org/abs/1", "type": "paper", "title": "Foo: bar"}}
    b = Brief(stories=[Story(headline="A", why="w", primary_id=1, supporting_ids=[2, 2, 99]),
                       Story(headline="B", why="w", primary_id=2, supporting_ids=[]),   # 2 already used
                       Story(headline="C", why="w", primary_id=42, supporting_ids=[1])])  # invented primary
    out = assemble(b, pool, hot=0.75)
    assert len(out) == 1 and out[0]["hot"]
    assert [lk["label"] for lk in out[0]["links"]] == ["𝕏 @a", "paper: Foo"]


async def test_make_brief_saves_and_windows_from_last_brief(database):
    await seed()
    await database.execute("update items set auki_relevance = 0.9")
    b = await make_brief(since=NOW - timedelta(hours=1))
    assert b["stories"] and b["id"] and b["sources"]
    assert await make_brief() is None  # next brief starts where this one ended: nothing new
