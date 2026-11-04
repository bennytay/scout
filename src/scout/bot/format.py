import discord

TOPIC_EMOJI = {
    "manipulation": "🦾", "locomotion": "🦿", "humanoids": "🤖", "vla-foundation-models": "🧠", "sim2real": "🎮",
    "slam-spatial-mapping": "🗺️", "perception": "👁️", "hardware": "🔩", "datasets-benchmarks": "📊",
    "multi-agent": "🕸️", "other": "📌",
}
TYPE_COLOR = {"paper": 0x3B82F6, "repo": 0x22C55E, "post": 0x0EA5E9, "article": 0xA855F7,
              "model": 0xF59E0B, "dataset": 0xEF4444, "video": 0xEC4899}


def relevance_bar(r: float | None) -> str:
    if r is None:
        return "n/a"
    filled = round(r * 10)
    return f"{'█' * filled}{'░' * (10 - filled)} {r:.2f}"


def item_embed(item: dict, header: str | None = None) -> discord.Embed:
    e = discord.Embed(
        title=item["title"][:250], url=item["url"], description=(item.get("summary") or "")[:1500],
        color=TYPE_COLOR.get(item.get("type"), 0x64748B),
    )
    if header:
        e.set_author(name=header)
    topics = " ".join(f"{TOPIC_EMOJI.get(t, '')} `{t}`" for t in item.get("topics", []))
    if topics:
        e.add_field(name="Topics", value=topics, inline=False)
    if item.get("auki_relevance_reason") or item.get("auki_relevance") is not None:
        e.add_field(name=f"Why it matters to Auki · {relevance_bar(item.get('auki_relevance'))}",
                    value=(item.get("auki_relevance_reason") or "–")[:1000], inline=False)
    people = ", ".join(item.get("authors", [])[:6]) + ("…" if len(item.get("authors", [])) > 6 else "")
    if people or item.get("orgs"):
        e.add_field(name="Who", value=" · ".join(x for x in [people, ", ".join(item.get("orgs", [])[:4])] if x)[:1000],
                    inline=False)
    related = item.get("related") or []
    if related:
        e.add_field(name="Related in Scout", inline=False, value="\n".join(
            f"• [{r['title'][:80]}]({r['url']}) · _{r.get('relation', 'similar')}_" for r in related[:4]))
    seen = ", ".join(item.get("seen_in", []))
    e.set_footer(text=f"#{item['id']} · {item.get('type')} · seen in: {seen} · react 👍/👎 to tune relevance")
    return e
