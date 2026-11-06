"""Discord replies are embed cards: concise, everything a link, within Discord's embed limits."""
from datetime import UTC, datetime

from scout.bot import format as fmt
from scout.bot.format import brief_messages, source_failed


def item(n: int, rel: float, **kw) -> dict:
    return {"id": n, "title": f"Paper {n} about [robots]", "url": f"https://arxiv.org/abs/2611.{n:05d}",
            "type": "paper", "auki_relevance": rel, "auki_relevance_reason": f"Reason {n}.", **kw}


def test_link_card_fields():
    card = fmt.link_card(item(7, 0.82, importance=0.64, summary="First sentence here. Second ignored.",
                              topics=["slam-spatial-mapping"], authors=["A", "B", "C", "D"], orgs=["ETH Zurich"],
                              published_at="2026-11-05",
                              related=[{"title": "Repo", "url": "https://github.com/a/b", "type": "repo"}]))
    f = {x["name"]: x["value"] for x in card["fields"]}
    assert card["title"] == "📄 Paper 7 about [robots]" and card["url"] == "https://arxiv.org/abs/2611.00007"
    assert f["What"] == "First sentence here." and f["Why Auki"] == "Reason 7."
    assert f["Who"] == "A, B, C et al. · ETH Zurich" and f["Related"] == "[Repo](https://github.com/a/b)"
    assert card["footer"]["text"] == "importance 0.64 · 🔥 Auki" and card["timestamp"].startswith("2026-11-05")


def test_link_card_duplicate_and_failure():
    card = fmt.link_card(item(1, 0.5, seen_in=["arxiv", "huggingface"]), duplicate=True)
    assert "already tracked (seen in arXiv, Hugging Face)" in card["footer"]["text"]
    assert source_failed("github", ["HTTPStatusError 403 rate limit"]).startswith("⚠️ **GitHub** failed:")


def test_item_row_is_headline_then_small_meta():
    post = {"id": 1, "type": "post", "title": "@lab: raw text", "summary": "Lab ships a robot. More detail.",
            "url": "https://x.com/lab/status/9", "published_at": "2026-11-06", "importance": 0.7}
    row = fmt.item_row(1, post, [{"type": "paper", "url": "https://arxiv.org/abs/1"}])
    assert row == ("**1. [Lab ships a robot](https://x.com/lab/status/9)**\n"
                   "-# 𝕏 @lab · 6 Nov · importance 0.70 · [Paper](https://arxiv.org/abs/1)")


def test_topic_author_recent_cards():
    items = [{"id": i, "type": "paper", "title": f"Paper {i}", "url": f"https://arxiv.org/abs/{i}",
              "importance": 0.5, "media": {"image": "https://pbs.twimg.com/i.jpg"} if i == 2 else {}}
             for i in range(1, 4)]
    card = fmt.topic_card("vla-foundation-models", 14, items, {}, 60)
    assert card["title"] == "🏷️ VLA foundation models" and "60+ stored" in card["description"]
    assert card["thumbnail"]["url"].endswith("i.jpg") and "**3. [Paper 3]" in card["description"]
    assert "Nothing stored" in fmt.topic_card("humanoids", 7, [], {}, 0)["description"]
    many = [dict(items[0], id=n, title="x" * 200) for n in range(60)]
    assert len(fmt.topic_card("humanoids", 7, many, {}, 60)["description"]) <= 4096  # Discord's embed limit

    prof = fmt.author_card({"name": "Marco Hutter", "x_handle": "mhutter", "items_in_db": 4, "avatar": "https://a",
                            "topics": [{"topic": "locomotion", "n": 3}], "orgs": [{"name": "ETH Zurich"}],
                            "frequent_coauthors": [{"name": "Gen Li"}], "recent_items": items[:1]})
    assert prof["title"] == "👤 Marco Hutter" and prof["url"] == "https://x.com/mhutter"
    assert [f["name"] for f in prof["fields"]] == ["Items stored", "Locomotion"]
    assert prof["description"].startswith("-# ETH Zurich · works with Gen Li")

    stats, top = fmt.recent_cards({"days": 3, "total": 391, "by_type": {"paper": 258, "post": 64}, "top": items}, {})
    assert [f["name"] for f in stats["fields"]] == ["📄 papers", "💬 X posts"] and stats["fields"][0]["value"] == "**258**"
    assert top["description"].count("\n-# ") == 3


def brief(n_stories: int, why: str = "Why it matters.") -> dict:
    return {"window_end": datetime(2026, 11, 5, 9, 0, tzinfo=UTC), "n_new_items": 120, "sources": {"x": 12},
            "stories": [{"headline": f"Headline {i}", "why": why, "hot": i == 1,
                         "links": [{"label": "𝕏 @lab", "url": f"https://x.com/lab/status/{i}", "item_id": i},
                                   {"label": "paper: Foo", "url": f"https://arxiv.org/abs/2611.{i:05d}", "item_id": 100 + i}]}
                        for i in range(1, n_stories + 1)]}


def test_brief_is_a_header_then_one_card_per_story():
    items = {1: {"media": {"image": "https://pbs.twimg.com/a.jpg", "avatar": "https://pbs.twimg.com/av.jpg"},
                 "metrics": {"x_likes": 1234, "x_reposts": 56}, "importance": 0.91,
                 "published_at": datetime(2026, 11, 4, 11, 12, tzinfo=UTC)},
             2: {"media": {"image": "https://pbs.twimg.com/b.jpg"}, "metrics": {}, "importance": 0.5}}
    [msg] = brief_messages(brief(3), items, "Thu 5 Nov")
    assert msg["content"] == "📰 **Robotics brief** · Thu 5 Nov · 3 stories from 120 new items"
    first, second, third = msg["embeds"]
    assert first["title"] == "1. Headline 1" and first["url"] == "https://x.com/lab/status/1"
    assert first["author"] == {"name": "@lab", "url": "https://x.com/lab/status/1",
                               "icon_url": "https://pbs.twimg.com/av.jpg"}
    assert first["description"] == "Why it matters.\n[paper: Foo](https://arxiv.org/abs/2611.00001)"
    assert first["footer"]["text"] == "❤ 1,234 · 🔁 56 · importance 0.91 · 🔥 Auki"
    assert first["image"]["url"].endswith("a.jpg") and first["color"] != second["color"]  # orange = Auki
    assert first["timestamp"] == "2026-11-04T11:12:00+00:00"  # Discord shows the post date in the footer
    assert "thumbnail" in second and "image" not in second  # only the top story gets the big picture
    assert "image" not in third and "thumbnail" not in third and "footer" not in third  # no data: plain card


def test_brief_splits_under_discords_embed_limits():
    msgs = brief_messages(brief(14, why="W" * 210))
    assert len(msgs) >= 2 and msgs[0]["content"] and msgs[1]["content"] is None
    assert all(len(m["embeds"]) <= 10 for m in msgs)
    assert sum(len(m["embeds"]) for m in msgs) == 14


def test_ask_card_cites_dated_sources_and_fits():
    r = {"answer": "Two groups work on it [1][2]. " * 300,
         "sources": [{"n": n, "title": f"Source {n}", "url": f"https://arxiv.org/abs/2611.{n:05d}", "type": "paper",
                      "published_at": "2026-11-05"} for n in (1, 2)]}
    card = fmt.ask_card(r, "who works on it?")
    assert len(card["description"]) <= 4096 and card["author"]["name"] == "who works on it?"
    assert card["description"].endswith("-# [2] [Source 2](https://arxiv.org/abs/2611.00002) · Paper · 5 Nov")
    assert fmt.ask_card({"answer": "Nothing found.", "sources": []})["description"] == "Nothing found."
