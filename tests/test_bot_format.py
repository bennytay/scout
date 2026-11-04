"""Discord messages: concise, bulleted, everything a link, never over Discord's 2000-char limit."""
from scout.bot.format import link_reply, source_failed, source_update


def item(n: int, rel: float, **kw) -> dict:
    return {"id": n, "title": f"Paper {n} about [robots]", "url": f"https://arxiv.org/abs/2611.{n:05d}",
            "type": "paper", "auki_relevance": rel, "auki_relevance_reason": f"Reason {n}.", **kw}


def test_source_update_sorts_highlights_and_truncates():
    msg = source_update("arxiv", [item(1, 0.3), item(2, 0.9), item(3, 0.5)] + [item(i, 0.35) for i in range(4, 20)]
                        + [item(99, 0.0)])
    lines = msg.splitlines()
    assert lines[0] == "📡 **arXiv** · 19 new · 1 🔥 · 1 off-topic hidden"
    assert lines[1].startswith("• 📄 [Paper 2 about (robots)](<https://arxiv.org/abs/2611.00002>) · 🔥 0.90")
    assert lines[2] == "  ↳ Reason 2."                       # reason only for highlighted items
    assert "Reason 1." not in msg and "…+11 more" in lines[-1]  # 8 shown, rest summarised
    assert "](<https://" in msg                                 # links never unfurl into preview cards


def test_source_update_stays_under_discord_limit():
    many = [item(i, 0.95, title="T" * 300, auki_relevance_reason="R" * 400) for i in range(50)]
    assert len(source_update("huggingface", many, show=50)) <= 2000


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
