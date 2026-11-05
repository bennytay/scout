"""Discord messages: concise, bulleted, everything a link, never over Discord's 2000-char limit."""
from datetime import UTC, datetime

from scout.bot.format import brief_messages, link_reply, source_failed


def item(n: int, rel: float, **kw) -> dict:
    return {"id": n, "title": f"Paper {n} about [robots]", "url": f"https://arxiv.org/abs/2611.{n:05d}",
            "type": "paper", "auki_relevance": rel, "auki_relevance_reason": f"Reason {n}.", **kw}


def test_link_reply_is_four_bullets():
    msg = link_reply(item(7, 0.82, importance=0.64, summary="First sentence here. Second sentence ignored.", topics=["slam-spatial-mapping"],
                          authors=["A", "B", "C", "D"], orgs=["ETH Zurich"],
                          related=[{"title": "Repo", "url": "https://github.com/a/b"}]))
    lines = msg.splitlines()
    assert lines[0].endswith("· importance 0.64 · 🔥 Auki") and len(lines) == 5
    assert lines[1] == "• **What:** First sentence here."
    assert lines[3] == "• **Topics:** slam-spatial-mapping · **Who:** A, B, C et al. · ETH Zurich"
    assert lines[4] == "• **Related:** [Repo](<https://github.com/a/b>)"


def test_link_reply_duplicate_and_failure():
    assert "already tracked (seen in arXiv, Hugging Face)" in link_reply(
        item(1, 0.5, seen_in=["arxiv", "huggingface"]), duplicate=True)
    assert source_failed("github", ["HTTPStatusError 403 rate limit"]).startswith("⚠️ **GitHub** failed:")



def brief(n_stories: int, why: str = "Why it matters.") -> dict:
    return {"window_end": datetime(2026, 11, 5, 9, 0, tzinfo=UTC), "n_new_items": 120, "sources": {"x": 12},
            "stories": [{"headline": f"Headline {i}", "why": why, "hot": i == 1,
                         "links": [{"label": "𝕏 @lab", "url": f"https://x.com/lab/status/{i}", "item_id": i},
                                   {"label": "paper: Foo", "url": f"https://arxiv.org/abs/2611.{i:05d}", "item_id": 100 + i}]}
                        for i in range(1, n_stories + 1)]}


def test_brief_is_a_header_then_one_card_per_story():
    items = {1: {"media": {"image": "https://pbs.twimg.com/a.jpg", "avatar": "https://pbs.twimg.com/av.jpg"},
                 "metrics": {"x_likes": 1234, "x_reposts": 56}, "importance": 0.91},
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
    assert "thumbnail" in second and "image" not in second  # only the top story gets the big picture
    assert "image" not in third and "thumbnail" not in third and "footer" not in third  # no data: plain card


def test_brief_splits_under_discords_embed_limits():
    msgs = brief_messages(brief(14, why="W" * 210))
    assert len(msgs) >= 2 and msgs[0]["content"] and msgs[1]["content"] is None
    assert all(len(m["embeds"]) <= 10 for m in msgs)
    assert sum(len(m["embeds"]) for m in msgs) == 14


def test_ask_reply_cites_sources_and_fits():
    from scout.bot.format import LIMIT, ask_reply

    r = {"answer": "Two groups work on it [1][2]. " * 200,
         "sources": [{"n": n, "title": f"Source {n}", "url": f"https://arxiv.org/abs/2611.{n:05d}"} for n in (1, 2)]}
    msg = ask_reply(r)
    assert len(msg) <= LIMIT and msg.endswith("[2] [Source 2](<https://arxiv.org/abs/2611.00002>)")
    assert ask_reply({"answer": "Nothing found.", "sources": []}) == "Nothing found."


def test_item_list_shows_what_a_post_links_to():
    from scout.bot.format import LIMIT, item_list

    post = {"id": 1, "title": "@physical_int: pi-0.7 is out", "url": "https://x.com/physical_int/status/1",
            "type": "post", "auki_relevance": 0.7, "published_at": "2026-11-04"}
    links = {1: [{"type": "paper", "title": "pi-0.7: A Generalist Policy", "url": "https://arxiv.org/abs/2611.00001"},
                 {"type": "repo", "title": "Physical-Intelligence/openpi: code", "url": "https://github.com/Physical-Intelligence/openpi"}]}
    msg = item_list("🏷️ **vla**", [post], links)
    assert "[paper: pi-0.7](<https://arxiv.org/abs/2611.00001>)" in msg and "[code: openpi]" in msg
    assert "💬 [@physical_int: pi-0.7 is out](<https://x.com/physical_int/status/1>) · 0.70 · 2026-11-04" in msg
    hot = item_list("h", [dict(post, importance=0.9, auki_relevance=0.8)])
    assert "· 0.90 🔥 · 2026-11-04" in hot  # importance shown; 🔥 marks Auki relevance
    many = [dict(post, id=n, title=f"Post {n} " + "x" * 80) for n in range(60)]
    assert len(item_list("h", many)) <= LIMIT and item_list("h", many).endswith("…")
    assert item_list("h", []) == "h\nNothing stored yet."


def test_author_reply():
    from scout.bot.format import author_reply

    msg = author_reply({"name": "Sergey Levine", "x_handle": "svlevine", "items_in_db": 3,
                        "topics": [{"topic": "manipulation", "n": 2}], "orgs": [{"name": "UC Berkeley"}],
                        "frequent_coauthors": [{"name": "Chelsea Finn"}],
                        "recent_items": [item(1, 0.5)]})
    assert msg.splitlines()[0] == "👤 **Sergey Levine** ([@svlevine](<https://x.com/svlevine>)) · 3 items"
    assert "• **Topics:** manipulation (2)" in msg and "Paper 1 about (robots)" in msg
