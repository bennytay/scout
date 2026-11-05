"""Discord message formatting: short, everything a link. Pure functions (unit-tested, previewable)."""
import re

LABEL = {"arxiv": "arXiv", "github": "GitHub", "huggingface": "Hugging Face", "hackernews": "Hacker News",
         "alphaxiv": "alphaXiv", "rss": "RSS", "x": "X", "discord": "Discord"}
ICON = {"paper": "📄", "repo": "💻", "post": "💬", "article": "📰", "model": "🧠", "dataset": "🗂️", "video": "🎬"}
LIMIT = 1900  # Discord hard limit is 2000


def _cut(text: str | None, n: int) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def _link(title: str, url: str, n: int = 90) -> str:
    title = _cut(title, n).replace("[", "(").replace("]", ")")
    return f"[{title}](<{url}>)"  # <...> stops Discord unfurling a preview card


def _first_sentence(text: str | None) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip(), maxsplit=1)
    return parts[0] if parts else ""


def source_failed(source: str, errors: list[str]) -> str:
    return f"⚠️ **{LABEL.get(source, source)}** failed: `{_cut(errors[0] if errors else 'unknown error', 160)}`"


def link_reply(item: dict, duplicate: bool = False) -> str:
    """Reply to a team-shared link: 4 bullets."""
    head = f"{ICON.get(item.get('type'), '🔗')} **{_link(item['title'], item['url'], 110)}**"
    if item.get("importance") is not None:
        head += f" · importance {item['importance']:.2f}"
    if (item.get("auki_relevance") or 0) >= 0.75:
        head += " · 🔥 Auki"
    if duplicate:
        head += f" · already tracked (seen in {', '.join(LABEL.get(s, s) for s in item.get('seen_in', []))})"
    who = ", ".join(item.get("authors", [])[:3]) + (" et al." if len(item.get("authors", [])) > 3 else "")
    who = " · ".join(x for x in [who, ", ".join(item.get("orgs", [])[:3])] if x)
    related = item.get("related") or []
    bullets = [
        f"• **What:** {_cut(_first_sentence(item.get('summary')), 220)}",
        f"• **Why Auki:** {_cut(item.get('auki_relevance_reason'), 220)}" if item.get("auki_relevance_reason") else None,
        f"• **Topics:** {', '.join(item.get('topics', []))}" + (f" · **Who:** {_cut(who, 100)}" if who else ""),
        "• **Related:** " + ", ".join(_link(r["title"], r["url"], 50) for r in related[:3]) if related else None,
    ]
    return "\n".join([head] + [b for b in bullets if b])[:LIMIT]


def render_brief(b: dict, x_monitored: bool = True) -> list[str]:
    """The brief as Discord messages (split at story boundaries to stay under the 2000-char limit)."""
    end = b["window_end"]
    head = (f"📰 **Robotics brief** · {end:%a %d %b, %H:%M} UTC · {b['n_new_items']} new items → "
            f"{len(b['stories'])} stories")
    blocks = []
    for n, st in enumerate(b["stories"], 1):
        links = " · ".join(f"[{_cut(lk['label'], 40)}](<{lk['url']}>)" for lk in st["links"])
        blocks.append(f"**{n}. {_cut(st['headline'], 110)}**{' 🔥' if st.get('hot') else ''}\n"
                      f"{_cut(st['why'], 200)}\n{links}")
    counts = b.get("sources") or {}
    mon = [f"{LABEL.get(k, k)} {v}" for k, v in counts.items() if k not in ("discord", "web", "mcp")]
    if not x_monitored and "x" not in counts:
        mon.append("X (team links only)")
    foot = "📡 Monitored: " + " · ".join(mon) if mon else ""
    msgs, cur = [], head
    for blk in blocks + ([foot] if foot else []):
        if len(cur) + len(blk) + 2 > LIMIT:
            msgs.append(cur)
            cur = blk
        else:
            cur += "\n\n" + blk
    msgs.append(cur)
    return msgs


# ---------- replies to @Scout and slash commands ----------

def _fit(lines: list[str]) -> str:
    """Join lines, dropping whole lines from the end to stay under Discord's limit."""
    out = []
    for ln in lines:
        if len("\n".join(out + [ln])) > LIMIT - 20:
            out.append("…")
            break
        out.append(ln)
    return "\n".join(out)


def item_line(item: dict, links: list[dict] | None = None) -> str:
    from ..brief import link_label

    line = f"{ICON.get(item.get('type'), '🔗')} {_link(item['title'], item['url'], 85)}"
    score = item.get("importance", item.get("auki_relevance"))
    if score is not None:
        line += f" · {score:.2f}"
    if (item.get("auki_relevance") or 0) >= 0.75:
        line += " 🔥"
    if item.get("published_at"):
        line += f" · {str(item['published_at'])[:10]}"
    if links:
        line += " · " + " · ".join(f"[{_cut(link_label(lk), 45)}](<{lk['url']}>)" for lk in links[:3])
    return line


def item_list(header: str, items: list[dict], links: dict[int, list[dict]] | None = None) -> str:
    if not items:
        return header + "\nNothing stored yet."
    links = links or {}
    return _fit([header] + [item_line(i, links.get(i["id"])) for i in items])


def ask_reply(r: dict) -> str:
    """@Scout answer: the answer with [n] citations, then the numbered sources as links."""
    answer = (r.get("answer") or "").strip()
    sources = [f"[{s['n']}] {_link(s['title'], s['url'], 80)}" for s in r.get("sources", [])]
    if not sources:
        return answer[:LIMIT]
    budget = LIMIT - len("\n".join(sources)) - 40
    if len(answer) > budget:
        answer = _cut(answer, max(budget, 300))
    return _fit([answer, ""] + sources)


def author_reply(p: dict) -> str:
    handle = f" ([@{p['x_handle']}](<https://x.com/{p['x_handle']}>))" if p.get("x_handle") else ""
    head = f"👤 **{p['name']}**{handle} · {p.get('items_in_db', 0)} items"
    lines = [head]
    if p.get("topics"):
        lines.append("• **Topics:** " + ", ".join(f"{t['topic']} ({t['n']})" for t in p["topics"][:5]))
    if p.get("orgs"):
        lines.append("• **Orgs:** " + ", ".join(o["name"] for o in p["orgs"][:4]))
    if p.get("frequent_coauthors"):
        lines.append("• **Works with:** " + ", ".join(c["name"] for c in p["frequent_coauthors"][:5]))
    lines += [item_line(i) for i in p.get("recent_items", [])[:8]]
    return _fit(lines)


def recent_reply(r: dict, links: dict[int, list[dict]]) -> str:
    by_type = " · ".join(f"{ICON.get(t, '🔗')} {n} {t}s" for t, n in r["by_type"].items()) or "nothing new"
    head = f"🗂️ **Last {r['days']} days:** {by_type} · {r['total']} items stored in total"
    return item_list(head, r["top"], links)


def radar_suggestion(handle: str, kept: int, judged: int) -> str:
    return (f"⭐ [@{handle}](<https://x.com/{handle}>) isn't on the radar, but {kept} of {judged} of their posts were "
            f"kept as news. Add them with `/follow {handle}`.")
