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


BLUE, ORANGE = 0x378ADD, 0xD85A30  # card colour bar: orange marks stories that matter to Auki
EMBEDS_PER_MSG, EMBED_CHARS = 10, 5500  # Discord: 10 embeds and 6000 characters per message


def _lead(story: dict) -> dict:
    """The story's lead link: its first X post, else its first link."""
    return next((lk for lk in story["links"] if lk["url"].startswith("https://x.com/")), story["links"][0])


def story_card(n: int, story: dict, item: dict | None, big_image: bool) -> dict:
    """One brief story as a Discord embed: poster, headline, why it matters, its other links, likes, picture."""
    item = item or {}
    lead = _lead(story)
    media, metrics = item.get("media") or {}, item.get("metrics") or {}
    others = [lk for lk in story["links"] if lk is not lead]
    body = _cut(story["why"], 220)
    if others:
        body += "\n" + " · ".join(f"[{_cut(lk['label'], 40)}]({lk['url']})" for lk in others[:4])
    card = {"title": _cut(f"{n}. {story['headline']}", 250), "url": lead["url"], "description": body,
            "color": ORANGE if story.get("hot") else BLUE}
    if lead["url"].startswith("https://x.com/"):
        card["author"] = {"name": "@" + lead["url"].split("/")[3], "url": lead["url"]}
        if media.get("avatar"):
            card["author"]["icon_url"] = media["avatar"]
    foot = []
    if metrics.get("x_likes"):
        foot.append(f"❤ {int(metrics['x_likes']):,}")
    if metrics.get("x_reposts"):
        foot.append(f"🔁 {int(metrics['x_reposts']):,}")
    if item.get("importance") is not None:
        foot.append(f"importance {item['importance']:.2f}")
    if story.get("hot"):
        foot.append("🔥 Auki")
    if foot:
        card["footer"] = {"text": " · ".join(foot)}
    if media.get("image"):
        card["image" if big_image else "thumbnail"] = {"url": media["image"]}
    if item.get("published_at"):
        card["timestamp"] = item["published_at"].isoformat()  # Discord shows it in each reader's timezone
    return card


def _card_chars(card: dict) -> int:
    return sum(len(card.get(k) or "") for k in ("title", "description")) + len(
        (card.get("author") or {}).get("name", "")) + len((card.get("footer") or {}).get("text", ""))


def brief_messages(b: dict, items: dict[int, dict] | None = None, when: str | None = None) -> list[dict]:
    """The brief as Discord messages: a one-line header, then one card per story (the top story with a big
    picture). `items` maps item id -> {media, metrics, importance} for each story's lead link."""
    items = items or {}
    when = when or f"{b['window_end']:%a %-d %b}"
    head = f"📰 **Robotics brief** · {when} · {len(b['stories'])} stories from {b['n_new_items']} new items"
    cards = [story_card(n, st, items.get(_lead(st).get("item_id")), big_image=n == 1)
             for n, st in enumerate(b["stories"], 1)]
    msgs, cur, size = [], [], 0
    for c in cards:
        if cur and (len(cur) == EMBEDS_PER_MSG or size + _card_chars(c) > EMBED_CHARS):
            msgs.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += _card_chars(c)
    if cur:
        msgs.append(cur)
    return [{"content": head if i == 0 else None, "embeds": m} for i, m in enumerate(msgs)] or [{"content": head,
                                                                                                "embeds": []}]


# ---------- replies to @Scout and slash commands: one card each ----------

PURPLE, TEAL, CLAY = 0x7F77DD, 0x1D9E75, 0xD85A30
TAG = {"paper": "Paper", "repo": "Code", "model": "Model", "dataset": "Dataset", "article": "Page",
       "video": "Video", "post": "Post"}
TYPE_NAME = {"paper": "papers", "post": "X posts", "model": "models", "dataset": "datasets", "article": "articles",
             "repo": "repos", "video": "videos"}
DESC_LIMIT = 3900  # Discord: 4096 characters per embed description


def _date(d) -> str:
    """'6 Nov' from a date, datetime or ISO string."""
    from datetime import date, datetime

    if not d:
        return ""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    if isinstance(d, datetime):
        d = d.date()
    return f"{d.day} {d:%b}"


def _headline(item: dict) -> str:
    """A readable headline. Post titles are raw post text ('@handle: …'), so posts use the first sentence of
    Claude's summary instead; the handle goes on the meta line."""
    if item.get("type") == "post" and (first := _first_sentence(item.get("summary"))):
        return first.rstrip(".")
    return re.sub(r"^@\w+:\s*", "", item["title"]) or item["title"]


def topic_name(slug: str) -> str:
    caps = {"vla": "VLA", "slam": "SLAM", "ai": "AI", "3d": "3D", "rl": "RL"}
    words = [caps.get(w, w) for w in slug.split("-")]
    return " ".join([words[0][:1].upper() + words[0][1:]] + words[1:])


def _handle(item: dict) -> str | None:
    m = re.match(r"https://x\.com/(\w+)/status/", item.get("url") or "")
    return m.group(1) if m else None


def item_row(n: int | None, item: dict, links: list[dict] | None = None) -> str:
    """Two lines: the linked headline, then small grey meta (who · date · importance · linked paper/code)."""
    title = _cut(_headline(item), 90).replace("[", "(").replace("]", ")")
    head = f"**{f'{n}. ' if n else ''}[{title}]({item['url']})**"
    who = f"𝕏 @{h}" if (h := _handle(item)) else f"{ICON.get(item.get('type'), '🔗')} {TAG.get(item.get('type'), 'Link')}"
    meta = [who, _date(item.get("published_at"))]
    if item.get("importance") is not None:
        meta.append(f"importance {item['importance']:.2f}")
    if (item.get("auki_relevance") or 0) >= 0.75:
        meta.append("🔥 Auki")
    meta += [f"[{TAG.get(lk.get('type'), 'Link')}]({lk['url']})" for lk in (links or [])[:3]]
    return head + "\n-# " + " · ".join(m for m in meta if m)


def _rows(items: list[dict], links: dict[int, list[dict]] | None, budget: int, numbered: bool = True) -> str:
    out = ""
    for n, it in enumerate(items, 1):
        row = item_row(n if numbered else None, it, (links or {}).get(it.get("id")))
        if len(out) + len(row) + 2 > budget:
            break
        out += ("\n\n" if out else "") + row
    return out


def _picture(items: list[dict]) -> dict | None:
    for it in items:
        if img := (it.get("media") or {}).get("image"):
            return {"url": img}
    return None


def topic_card(topic: str, days: int, items: list[dict], links: dict[int, list[dict]], total: int) -> dict:
    name = topic_name(topic)
    if not items:
        return {"title": f"🏷️ {name}", "color": PURPLE, "description": f"Nothing stored in the last {days} days."}
    more = f"{total}+" if total >= 50 else str(total)
    sub = f"-# Most important first · last {days} days · {more} stored\n\n"
    card = {"title": f"🏷️ {name}", "color": PURPLE, "description": sub + _rows(items, links, DESC_LIMIT - len(sub))}
    if pic := _picture(items):
        card["thumbnail"] = pic
    if total > len(items):
        card["footer"] = {"text": f"Top {len(items)} shown · /topic with more days to go further back"}
    return card


def author_card(p: dict) -> dict:
    handle = p.get("x_handle")
    line = " · ".join(x for x in [", ".join(o["name"] for o in p.get("orgs", [])[:2]),
                                  ("works with " + ", ".join(c["name"] for c in p.get("frequent_coauthors", [])[:3]))
                                  if p.get("frequent_coauthors") else ""] if x)
    desc = (f"-# {line}\n\n" if line else "") + "**Recent**\n" + _rows(
        p.get("recent_items", [])[:8], {i.get("id"): i.get("links") for i in p.get("recent_items", [])}, 3000)
    card = {"title": f"👤 {p['name']}", "color": TEAL, "description": desc,
            "fields": [{"name": "Items stored", "value": f"**{p.get('items_in_db', 0)}**", "inline": True}]
            + [{"name": topic_name(t["topic"]), "value": f"**{t['n']}**", "inline": True}
               for t in p.get("topics", [])[:2]]}
    if handle:
        card["url"] = f"https://x.com/{handle}"
        card["author"] = {"name": f"@{handle}", "url": card["url"]}
    if p.get("avatar"):
        card["thumbnail"] = {"url": p["avatar"]}
    return card


def recent_cards(r: dict, links: dict[int, list[dict]]) -> list[dict]:
    """Two cards: what's stored (counts), then the top stories."""
    stats = {"title": f"🗂️ What's stored · last {r['days']} days", "color": BLUE,
             "description": f"-# {r['total']:,} items in the database in total",
             "fields": [{"name": f"{ICON.get(t, '🔗')} {TYPE_NAME.get(t, t + 's')}", "value": f"**{n:,}**", "inline": True}
                        for t, n in list(r["by_type"].items())[:9]] or
                       [{"name": "Nothing new", "value": "No items stored in this window.", "inline": False}]}
    if not r["top"]:
        return [stats]
    top = {"title": "Top stories", "color": BLUE, "description": _rows(r["top"], links, DESC_LIMIT)}
    if pic := _picture(r["top"]):
        top["thumbnail"] = pic
    return [stats, top]


def ask_card(r: dict, question: str | None = None) -> dict:
    """@Scout answer with [n] citations, then the numbered sources (dated, tagged)."""
    sources = r.get("sources", [])
    lines = []
    for x in sources:
        who = f"𝕏 @{h}" if (h := _handle(x)) else TAG.get(x.get("type"), "Link")
        title = _cut(_headline(x), 70).replace("[", "(").replace("]", ")")
        lines.append(f"-# [{x['n']}] [{title}]({x['url']}) · {who}" + (f" · {_date(x.get('published_at'))}"
                                                                         if x.get("published_at") else ""))
    tail = ("\n\n**Sources**\n" + "\n".join(lines)) if lines else ""
    answer = _cut((r.get("answer") or "").strip(), DESC_LIMIT - len(tail) - 10)
    card = {"description": answer + tail, "color": CLAY,
            "footer": {"text": "Answered only from what Scout has stored"}}
    if question:
        card["author"] = {"name": _cut(question, 250)}
    return card


def link_card(item: dict, duplicate: bool = False) -> dict:
    """Reply to a team-shared link: what it is, why it matters, topics and who, related items."""
    who = ", ".join(item.get("authors", [])[:3]) + (" et al." if len(item.get("authors", [])) > 3 else "")
    who = " · ".join(x for x in [who, ", ".join(item.get("orgs", [])[:3])] if x)
    fields = [{"name": "What", "value": _cut(_first_sentence(item.get("summary")), 300) or "—", "inline": False}]
    if item.get("auki_relevance_reason"):
        fields.append({"name": "Why Auki", "value": _cut(item["auki_relevance_reason"], 300), "inline": False})
    if item.get("topics"):
        fields.append({"name": "Topics", "value": ", ".join(item["topics"]), "inline": True})
    if who:
        fields.append({"name": "Who", "value": _cut(who, 200), "inline": True})
    if rel := item.get("related") or []:
        fields.append({"name": "Related", "value": "\n".join(
            f"[{_cut(_headline(x), 60)}]({x['url']})" for x in rel[:3]), "inline": False})
    foot = [f"importance {item['importance']:.2f}"] if item.get("importance") is not None else []
    if (item.get("auki_relevance") or 0) >= 0.75:
        foot.append("🔥 Auki")
    if duplicate:
        foot.append("already tracked (seen in " + ", ".join(LABEL.get(s, s) for s in item.get("seen_in", [])) + ")")
    card = {"title": f"{ICON.get(item.get('type'), '🔗')} {_cut(_headline(item), 240)}", "url": item["url"],
            "color": ORANGE if (item.get("auki_relevance") or 0) >= 0.75 else BLUE, "fields": fields}
    if foot:
        card["footer"] = {"text": " · ".join(foot)}
    media = item.get("media") or {}
    if h := _handle(item):
        card["author"] = {"name": f"@{h}", "url": item["url"], **({"icon_url": media["avatar"]} if media.get("avatar") else {})}
    if media.get("image"):
        card["thumbnail"] = {"url": media["image"]}
    if item.get("published_at"):
        card["timestamp"] = f"{item['published_at']}T00:00:00Z" if len(str(item["published_at"])) == 10 else str(item["published_at"])
    return card


def radar_suggestion(handle: str, kept: int, judged: int) -> str:
    return (f"⭐ [@{handle}](<https://x.com/{handle}>) isn't on the radar, but {kept} of {judged} of their posts were "
            f"kept as news. Add them with `/follow {handle}`.")
