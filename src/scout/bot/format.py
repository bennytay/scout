"""Discord message formatting: short bullets, everything a link. Pure functions (unit-tested, previewable)."""
import re

LABEL = {"arxiv": "arXiv", "github": "GitHub", "huggingface": "Hugging Face", "hackernews": "Hacker News",
         "alphaxiv": "alphaXiv", "rss": "RSS", "x": "X", "discord": "Discord"}
ICON = {"paper": "📄", "repo": "💻", "post": "💬", "article": "📰", "model": "🧠", "dataset": "🗂️", "video": "🎬"}
LIMIT = 1900  # Discord hard limit is 2000
OFF_TOPIC = 0.3  # below this the LLM judged it not robotics-relevant: counted, not shown


def _cut(text: str | None, n: int) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def _link(title: str, url: str, n: int = 90) -> str:
    title = _cut(title, n).replace("[", "(").replace("]", ")")
    return f"[{title}](<{url}>)"  # <...> stops Discord unfurling a preview card


def _first_sentence(text: str | None) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip(), maxsplit=1)
    return parts[0] if parts else ""


def _score(r: float | None, hot: float) -> str:
    return f" · 🔥 {r:.2f}" if r is not None and r >= hot else ""


def source_update(source: str, items: list[dict], hot: float = 0.75, show: int = 8) -> str:
    """One message per source run: what's new, most Auki-relevant first."""
    total = len(items)
    items = sorted((i for i in items if (i.get("auki_relevance") or 0) >= OFF_TOPIC),
                   key=lambda i: i.get("auki_relevance") or 0, reverse=True)
    n_hot = sum(1 for i in items if (i.get("auki_relevance") or 0) >= hot)
    name = LABEL.get(source, source)
    if not items:
        return f"📡 **{name}** · {total} checked, none relevant"
    head = f"📡 **{name}** · {len(items)} new" + (f" · {n_hot} 🔥" if n_hot else "")
    if total > len(items):
        head += f" · {total - len(items)} off-topic hidden"
    lines = [head]
    for i in items[:show]:
        line = f"• {ICON.get(i.get('type'), '•')} {_link(i['title'], i['url'])}{_score(i.get('auki_relevance'), hot)}"
        if (i.get("auki_relevance") or 0) >= hot and i.get("auki_relevance_reason"):
            line += f"\n  ↳ {_cut(i['auki_relevance_reason'], 140)}"
        if len("\n".join(lines + [line])) > LIMIT - 60:
            break
        lines.append(line)
    rest = len(items) - (len(lines) - 1)
    if rest > 0:
        lines.append(f"…+{rest} more (ask your LLM: `search(source=\"{source}\", since=\"1d\")`)")
    return "\n".join(lines)


def source_failed(source: str, errors: list[str]) -> str:
    return f"⚠️ **{LABEL.get(source, source)}** failed: `{_cut(errors[0] if errors else 'unknown error', 160)}`"


def link_reply(item: dict, duplicate: bool = False) -> str:
    """Reply to a team-shared link: 4 bullets."""
    head = f"{ICON.get(item.get('type'), '🔗')} **{_link(item['title'], item['url'], 110)}**"
    if item.get("auki_relevance") is not None:
        head += f" · relevance {item['auki_relevance']:.2f}"
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
