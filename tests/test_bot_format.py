"""Discord messages: concise, bulleted, everything a link, never over Discord's 2000-char limit."""
from datetime import UTC, datetime

from scout.bot.format import link_reply, render_brief, source_failed


def item(n: int, rel: float, **kw) -> dict:
    return {"id": n, "title": f"Paper {n} about [robots]", "url": f"https://arxiv.org/abs/2611.{n:05d}",
            "type": "paper", "auki_relevance": rel, "auki_relevance_reason": f"Reason {n}.", **kw}


def test_link_reply_is_four_bullets():
    msg = link_reply(item(7, 0.82, summary="First sentence here. Second sentence ignored.", topics=["slam-spatial-mapping"],
                          authors=["A", "B", "C", "D"], orgs=["ETH Zurich"],
                          related=[{"title": "Repo", "url": "https://github.com/a/b"}]))
    lines = msg.splitlines()
    assert lines[0].endswith("· relevance 0.82") and len(lines) == 5
    assert lines[1] == "• **What:** First sentence here."
    assert lines[3] == "• **Topics:** slam-spatial-mapping · **Who:** A, B, C et al. · ETH Zurich"
    assert lines[4] == "• **Related:** [Repo](<https://github.com/a/b>)"


def test_link_reply_duplicate_and_failure():
    assert "already tracked (seen in arXiv, Hugging Face)" in link_reply(
        item(1, 0.5, seen_in=["arxiv", "huggingface"]), duplicate=True)
    assert source_failed("github", ["HTTPStatusError 403 rate limit"]).startswith("⚠️ **GitHub** failed:")



def brief(n_stories: int, why: str = "Why it matters.") -> dict:
    return {"window_end": datetime(2026, 11, 5, 9, 0, tzinfo=UTC), "n_new_items": 120, "sources": {"arxiv": 80, "x": 12},
            "stories": [{"headline": f"Headline {i}", "why": why, "hot": i == 1,
                         "links": [{"label": "𝕏 @lab", "url": f"https://x.com/lab/status/{i}"},
                                   {"label": "paper: Foo", "url": f"https://arxiv.org/abs/2611.{i:05d}"}]}
                        for i in range(1, n_stories + 1)]}


def test_render_brief_is_numbered_linked_and_concise():
    [msg] = render_brief(brief(3))
    lines = msg.splitlines()
    assert lines[0] == "📰 **Robotics brief** · Thu 05 Nov, 09:00 UTC · 120 new items → 3 stories"
    assert "**1. Headline 1** 🔥" in lines and "**2. Headline 2**" in lines
    assert "[𝕏 @lab](<https://x.com/lab/status/1>) · [paper: Foo](<https://arxiv.org/abs/2611.00001>)" in lines
    assert lines[-1] == "📡 Monitored: arXiv 80 · X 12"


def test_render_brief_splits_at_story_boundaries():
    msgs = render_brief(brief(10, why="W" * 190), x_monitored=False)
    assert len(msgs) >= 2 and all(len(m) <= 2000 for m in msgs)
    assert all(not m.startswith("\n") for m in msgs) and "**10. Headline 10**" in msgs[-1]


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
