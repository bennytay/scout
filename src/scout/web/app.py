"""Scout web: browse, search and maintain the database directly, without an LLM.

    scout web            # http://127.0.0.1:8000  (set WEB_PASSWORD to require a login)

Uses the same hybrid search as MCP, so both always agree. Server-rendered HTML, no JS build, no extra deps.
"""
import asyncio
import base64
import json
import secrets
from contextlib import asynccontextmanager
from html import escape
from urllib.parse import urlencode

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from .. import db, health
from .. import search as s
from ..config import settings
from ..connectors import REGISTRY
from ..log import log
from ..models import TOPICS
from ..pipeline.run import ingest_url, run_connector
from ..pipeline.store import reenrich, set_topics
from .page import CSS

TYPES = ("paper", "repo", "post", "article", "model", "dataset", "video")
SOURCE_KINDS = ("arxiv_category", "arxiv_query", "x_account", "x_query", "github_org", "github_query",
                "hf_feed", "hn_query", "rss", "alphaxiv")
KIND_CONNECTOR = {k: c.name for c in REGISTRY.values() for k in c.kinds}
FILTERS = ("q", "author", "org", "topic", "type", "source", "since", "min_relevance", "sort", "all")
OFF_TOPIC = 0.3  # same floor as the Discord feed
_running: set[asyncio.Task] = set()


def h(x) -> str:
    return escape("" if x is None else str(x))


def qs(params: dict, **change) -> str:
    merged = {k: v for k, v in {**params, **change}.items() if v not in (None, "")}
    return "/?" + urlencode(merged)


def page(title: str, body: str, active: str = "") -> HTMLResponse:
    nav = "".join(f'<a href="{u}" class="{"on" if active == k else ""}">{n}</a>'
                  for k, u, n in [("search", "/", "Search"), ("authors", "/authors", "Authors"),
                                  ("sources", "/sources", "Sources & health")])
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{h(title)} · Scout</title>
<style>{CSS}</style></head><body>
<header><a class="logo" href="/">📡 Scout</a><nav>{nav}</nav>
<form class="add" method="post" action="/add"><input name="url" placeholder="Add a link: paper, repo, X post…" required>
<button>Add</button></form></header><main>{body}</main></body></html>""")


def rel_bar(r) -> str:
    if r is None:
        return '<span class="rel none">n/a</span>'
    r = float(r)
    cls = "hot" if r >= settings().alert_min_relevance else "mid" if r >= 0.4 else "low"
    return f'<span class="rel {cls}" title="Auki relevance"><i style="width:{r * 100:.0f}%"></i><b>{r:.2f}</b></span>'


def chips(values, key: str, params: dict) -> str:
    return "".join(f'<a class="chip" href="{qs(params, **{key: v})}">{h(v)}</a>' for v in values or [])


def people(names, params: dict, n: int = 4) -> str:
    out = ", ".join(f'<a href="/author?name={h(a)}">{h(a)}</a>' for a in (names or [])[:n])
    return out + (f" +{len(names) - n}" if names and len(names) > n else "")


def result_card(r: dict, params: dict) -> str:
    orgs = " · ".join(f'<a href="{qs(params, org=o)}">{h(o)}</a>' for o in r.get("orgs", [])[:3])
    seen = " ".join(f'<span class="src">{h(x)}</span>' for x in r.get("seen_in", []))
    why = f'<p class="why">↳ {h(r["auki_relevance_reason"])}</p>' if r.get("auki_relevance_reason") else ""
    return f"""<article class="card">
  <div class="top"><span class="type t-{h(r['type'])}">{h(r['type'])}</span>
    <a class="title" href="/item/{r['id']}">{h(r['title'])}</a> {rel_bar(r.get('auki_relevance'))}</div>
  <div class="meta">{h(r.get('published_at', ''))} · {people(r.get('authors'), params)}{' · ' + orgs if orgs else ''}
    · {seen} · <a href="{h(r['url'])}" target="_blank" rel="noopener">open ↗</a></div>
  <p class="sum">{h((r.get('summary') or '')[:320])}</p>{why}
  <div class="chips">{chips(r.get('topics'), 'topic', params)}</div>
</article>"""


async def facet_counts() -> dict:
    topics = await db.fetch("select topic_slug as v, count(*) as n from item_topics group by 1 order by 2 desc")
    types = await db.fetch("select type::text as v, count(*) as n from items group by 1 order by 2 desc")
    sources = await db.fetch("select source as v, count(distinct item_id) as n from item_sources group by 1 order by 2 desc")
    orgs = await db.fetch("""select o.name as v, count(*) as n from item_orgs io join orgs o on o.id = io.org_id
                             group by 1 order by 2 desc limit 12""")
    authors = await db.fetch("""select a.name as v, count(*) as n from item_authors ia join authors a on a.id = ia.author_id
                                group by 1 order by 2 desc limit 12""")
    return {"topic": topics, "type": types, "source": sources, "org": orgs, "author": authors}


def facet_block(title: str, key: str, rows: list[dict], params: dict) -> str:
    cur = params.get(key)
    items = "".join(
        f'<a class="{"on" if cur == r["v"] else ""}" href="{qs(params, **{key: None if cur == r["v"] else r["v"]})}">'
        f'<span>{h(r["v"])}</span><em>{r["n"]}</em></a>' for r in rows)
    return f'<section class="facet"><h4>{title}</h4>{items}</section>'


# ---------------------------------------------------------------- search
async def home(request: Request):
    p = {k: request.query_params.get(k) for k in FILTERS}
    p = {k: v.strip() for k, v in p.items() if v and v.strip()}
    try:
        min_rel = float(p["min_relevance"]) if p.get("min_relevance") else (None if p.get("all") else OFF_TOPIC)
        results = await s.search(query=p.get("q"), author=p.get("author"), org=p.get("org"), topic=p.get("topic"),
                                 type=p.get("type"), source=p.get("source"), since=p.get("since"),
                                 min_relevance=min_rel, limit=50)
        error = ""
    except ValueError as e:
        results, error = [], f'<p class="err">Bad filter: {h(e)}</p>'
    if p.get("sort") == "newest":
        results.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    elif p.get("sort") == "relevance":
        results.sort(key=lambda r: r.get("auki_relevance") or 0, reverse=True)
    f = await facet_counts()
    active = "".join(f'<a class="chip on" href="{qs(p, **{k: None})}">{k}: {h(v)} ✕</a>'
                     for k, v in p.items() if k not in ("q", "sort", "all"))
    total = await db.fetchrow("select count(*) as n, max(ingested_at) as last from items")
    sel = lambda name, opts, cur: (f'<select name="{name}"><option value="">{name}: any</option>' + "".join(  # noqa: E731
        f'<option {"selected" if cur == o else ""} value="{h(o)}">{h(lbl)}</option>' for o, lbl in opts) + "</select>")
    hidden = f'<input type="hidden" name="source" value="{h(p["source"])}">' if p.get("source") else ""
    form = f"""<form class="search" method="get" action="/">
  <input class="q" name="q" value="{h(p.get('q'))}" placeholder='Search by meaning, keyword, author or org. Try: robots sharing a map · "visual localization" -aerial · Levine' autofocus>
  <div class="row">
    {sel('topic', [(t, t) for t in TOPICS], p.get('topic'))}
    {sel('type', [(t, t) for t in TYPES], p.get('type'))}
    {sel('since', [('1d', 'last day'), ('7d', 'last week'), ('30d', 'last month')], p.get('since'))}
    {sel('min_relevance', [('0.4', 'Auki ≥ 0.4'), ('0.6', 'Auki ≥ 0.6'), ('0.75', 'Auki ≥ 0.75 🔥')], p.get('min_relevance'))}
    {sel('sort', [('newest', 'newest first'), ('relevance', 'most Auki-relevant')], p.get('sort'))}
    <input name="author" value="{h(p.get('author'))}" placeholder="author (fuzzy)">
    <input name="org" value="{h(p.get('org'))}" placeholder="org (fuzzy)">
    {hidden}
    <button>Search</button>
  </div></form>"""
    side = (facet_block("Topics", "topic", f["topic"], p) + facet_block("Types", "type", f["type"], p)
            + facet_block("Sources", "source", f["source"], p) + facet_block("Top orgs", "org", f["org"], p)
            + facet_block("Top authors", "author", f["author"], p))
    cards = "".join(result_card(r, p) for r in results) or '<p class="empty">No matches. Loosen a filter?</p>'
    how = ("ranked by hybrid search (keyword + meaning + fuzzy names)" if p.get("q")
           else "newest first (type a query for ranked search)")
    if not p.get("min_relevance"):
        how += (f' · <a href="{qs(p, all=None)}">hide off-topic</a>' if p.get("all")
                else f' · off-topic hidden (<a href="{qs(p, all="1")}">show</a>)')
    body = f"""{form}<div class="layout"><aside>{side}</aside><div>
  <div class="status">{len(results)} shown · {how} · {total['n']} items in the database{active and ' · ' + active}</div>
  {error}{cards}</div></div>"""
    return page(p.get("q") or "Search", body, "search")


# ---------------------------------------------------------------- item
async def item_page(request: Request):
    iid = int(request.path_params["id"])
    it = await s.get_item(iid)
    if not it:
        return page("Not found", '<p class="empty">No such item.</p>')
    row = await db.fetchrow("select curated_at, curated_note, enrich_model, full_text from items where id = %s", iid)
    ents = it.get("entities") or {}
    ent_html = "".join(f'<div><b>{h(k)}</b> {chips(v, "q", {})}</div>' for k, v in ents.items() if v)
    related = "".join(
        f'<li><span class="type t-{h(r["type"])}">{h(r["type"])}</span> <a href="/item/{r["id"]}">{h(r["title"])}</a>'
        f' <em>{h(r.get("relation"))}{" · " + str(r["similarity"]) if r.get("similarity") else ""}</em></li>'
        for r in it.get("related", []))
    metrics = " · ".join(f"{h(k)} {v:g}" for k, v in (it.get("metrics") or {}).items())
    boxes = "".join(f'<label><input type="checkbox" name="topics" value="{t}" {"checked" if t in it.get("topics", []) else ""}>{t}</label>'
                    for t in TOPICS)
    curated = (f'<p class="curated">✎ curated {h(str(row["curated_at"])[:16])}: {h(row["curated_note"])}</p>'
               if row["curated_at"] else "")
    full = (f'<details><summary>Full text ({len(row["full_text"])} chars)</summary><pre>{h(row["full_text"][:20000])}</pre></details>'
            if row["full_text"] else "")
    body = f"""<p><a href="/">← back to search</a></p>
<article class="card big">
  <div class="top"><span class="type t-{h(it['type'])}">{h(it['type'])}</span>
    <h1>{h(it['title'])}</h1></div>
  <div class="meta">{h(it.get('published_at', ''))} · seen in {h(', '.join(it.get('seen_in', [])))} · {metrics}
    · <a href="{h(it['url'])}" target="_blank" rel="noopener">{h(it['url'])} ↗</a></div>
  <p class="sum">{h(it.get('summary'))}</p>
  <div class="why big">{rel_bar(it.get('auki_relevance'))} {h(it.get('auki_relevance_reason'))}</div>{curated}
  <div class="kv"><div><b>Authors</b> {people(it.get('authors'), {}, 30) or '–'}</div>
    <div><b>Orgs</b> {chips(it.get('orgs'), 'org', {}) or '–'}</div>
    <div><b>Topics</b> {chips(it.get('topics'), 'topic', {})}</div>{ent_html}</div>
  {full}
</article>
<section class="card"><h3>Related</h3><ul class="related">{related or '<li>none yet</li>'}</ul></section>
<section class="card maint"><h3>Maintain</h3>
  <form method="post" action="/item/{iid}/curate">
    <div class="boxes">{boxes}</div>
    <div class="row"><label>Auki relevance <input name="relevance" type="number" min="0" max="1" step="0.05"
      value="{it.get('auki_relevance') or ''}"></label>
    <input name="note" placeholder="why (kept with the item)" value="">
    <button>Save curation</button></div>
  </form>
  <div class="row">
    <form method="post" action="/item/{iid}/reenrich"><button class="ghost">Re-run enrichment ({h(row['enrich_model'])})</button></form>
    <form method="post" action="/item/{iid}/delete" onsubmit="return confirm('Delete this item permanently?')">
      <button class="danger">Delete item</button></form>
  </div>
  <p class="hint">Curated topics and relevance are never overwritten by later re-enrichment.</p>
</section>"""
    return page(it["title"], body)


async def curate(request: Request):
    iid = int(request.path_params["id"])
    form = await request.form()
    topics = [t for t in form.getlist("topics") if t in TOPICS]
    note = (form.get("note") or "").strip() or "edited in web UI"
    if topics:
        await set_topics(iid, topics)
    rel = form.get("relevance")
    if rel not in (None, ""):
        await db.execute("update items set auki_relevance = %s where id = %s", max(0.0, min(1.0, float(rel))), iid)
    await db.execute("update items set curated_at = now(), curated_note = %s where id = %s", note, iid)
    return RedirectResponse(f"/item/{iid}", status_code=303)


async def reenrich_item(request: Request):
    iid = int(request.path_params["id"])
    await reenrich(iid)
    return RedirectResponse(f"/item/{iid}", status_code=303)


async def delete_item(request: Request):
    await db.execute("delete from items where id = %s", int(request.path_params["id"]))
    return RedirectResponse("/", status_code=303)


async def add_link(request: Request):
    url = ((await request.form()).get("url") or "").strip()
    r = await ingest_url(url, submitted_by="web") if url else None
    if r and r.item_id:
        return RedirectResponse(f"/item/{r.item_id}", status_code=303)
    return page("Add failed", f'<p class="err">Couldn\'t ingest {h(url)}: {h(r.error if r else "no url")}</p>')


# ---------------------------------------------------------------- authors
async def authors_page(request: Request):
    q = (request.query_params.get("q") or "").strip()
    if q:
        rows = await db.fetch(
            """select a.name, count(ia.item_id) as n from authors a left join item_authors ia on ia.author_id = a.id
               where %s <%% a.name or %s <%% a.normalized_name group by a.id
               order by max(word_similarity(%s, a.name)) desc, n desc limit 60""", q, q, q)
    else:
        rows = await db.fetch("""select a.name, count(*) as n from item_authors ia join authors a on a.id = ia.author_id
                                 group by a.id order by n desc, a.name limit 60""")
    items = "".join(f'<a class="person" href="/author?name={h(r["name"])}"><span>{h(r["name"])}</span><em>{r["n"]}</em></a>'
                    for r in rows)
    body = f"""<form class="search" method="get"><input class="q" name="q" value="{h(q)}"
      placeholder="Find an author (typo-tolerant): levine, chelsea fin, marco hutter…" autofocus></form>
      <div class="status">{'matches for ' + h(q) if q else 'most prolific in the database'}</div>
      <div class="people">{items or '<p class="empty">No authors match.</p>'}</div>"""
    return page("Authors", body, "authors")


async def author_page(request: Request):
    name = request.query_params.get("name", "")
    prof = await s.author_profile(name)
    if not prof:
        return page(name, f'<p class="empty">No author matching {h(name)}.</p>', "authors")
    items = await s.search(author=prof["name"], limit=50)
    topics = "".join(f'<a class="chip" href="{qs({"author": prof["name"]}, topic=t["topic"])}">{h(t["topic"])} <em>{t["n"]}</em></a>'
                     for t in prof.get("topics", []))
    co = "".join(f'<a class="person" href="/author?name={h(c["name"])}"><span>{h(c["name"])}</span><em>{c["n"]}</em></a>'
                 for c in prof.get("frequent_coauthors", []))
    orgs = chips([o["name"] for o in prof.get("orgs", [])], "org", {})
    handles = " · ".join(x for x in [prof.get("x_handle") and f'<a href="https://x.com/{h(prof["x_handle"])}">@{h(prof["x_handle"])}</a>',
                                     prof.get("github_handle") and f'GitHub {h(prof["github_handle"])}'] if x)
    body = f"""<p><a href="/authors">← authors</a></p><h1>{h(prof['name'])}</h1>
<div class="meta">{prof.get('items_in_db', 0)} items in Scout {('· ' + handles) if handles else ''}</div>
<div class="kv"><div><b>Topics</b> {topics or '–'}</div><div><b>Orgs</b> {orgs or '–'}</div></div>
<h3>Frequent co-authors</h3><div class="people">{co or '–'}</div>
<h3>Work</h3>{''.join(result_card(r, {'author': prof['name']}) for r in items)}"""
    return page(prof["name"], body, "authors")


# ---------------------------------------------------------------- sources & health
async def sources_page(request: Request):
    rows = await db.fetch("""select id, kind, value, enabled, added_by, last_run_at, last_success_at, last_error,
                                    consecutive_failures from sources order by kind, value""")
    runs = await db.fetch("""select distinct on (connector) connector, status, started_at, fetched, inserted, duplicates,
                                    cost_usd from ingest_runs order by connector, started_at desc""")
    spend = await db.fetchrow("""select coalesce(sum(cost_usd), 0)::float as total, count(*) as n,
                                        coalesce(sum(cost_usd) filter (where ingested_at > now() - interval '1 day'), 0)::float as day
                                 from items""")
    problems = await health.problems()
    have = {c.name: all(getattr(settings(), k) for k in c.needs) for c in REGISTRY.values()}

    def row(r):
        state = "🔴" if r["consecutive_failures"] >= 3 else "🟡" if r["consecutive_failures"] else "🟢" if r["last_success_at"] else "⚪"
        conn = KIND_CONNECTOR.get(r["kind"], "")
        note = "" if have.get(conn, True) else ' <span class="hint">needs API key</span>'
        return f"""<tr class="{'' if r['enabled'] else 'off'}"><td>{state}</td><td><code>{h(r['kind'])}</code></td>
  <td>{h(r['value'])}{note}<div class="err small">{h((r['last_error'] or '')[:160])}</div></td>
  <td>{h(str(r['last_success_at'] or '–')[:16])}</td>
  <td><form method="post" action="/sources/{r['id']}/toggle"><button class="ghost">{'disable' if r['enabled'] else 'enable'}</button></form></td>
  <td><form method="post" action="/sources/{r['id']}/run"><button class="ghost" {'disabled' if not r['enabled'] else ''}>run now</button></form></td></tr>"""

    run_rows = "".join(f"<tr><td>{h(r['connector'])}</td><td>{h(r['status'])}</td><td>{h(str(r['started_at'])[:16])}</td>"
                       f"<td>{r['fetched']}</td><td>{r['inserted']}</td><td>{r['duplicates']}</td><td>${float(r['cost_usd']):.4f}</td></tr>"
                       for r in runs)
    kinds = "".join(f"<option>{k}</option>" for k in SOURCE_KINDS)
    health_html = ("".join(f'<p class="err">🩺 {h(p)}</p>' for p in problems) or '<p class="ok">🩺 All healthy.</p>')
    running = f'<p class="hint">⏳ {len(_running)} run(s) in progress, refresh to update.</p>' if _running else ""
    body = f"""<div class="stats"><div><b>{spend['n']}</b> items</div><div><b>${spend['total']:.2f}</b> total LLM spend</div>
  <div><b>${spend['day']:.3f}</b> last 24h</div><div><b>{sum(1 for r in rows if r['enabled'])}</b> active sources</div></div>
{health_html}{running}
<section class="card"><h3>Track a new source</h3><form class="row" method="post" action="/sources/add">
  <select name="kind">{kinds}</select><input name="value" placeholder="cs.RO · physical_int · huggingface/lerobot · https://…/feed" required>
  <button>Add source</button></form></section>
<section class="card"><h3>Tracked sources</h3><table><tr><th></th><th>kind</th><th>value</th><th>last success</th><th></th><th></th></tr>
{''.join(row(r) for r in rows)}</table></section>
<section class="card"><h3>Latest run per connector</h3><table><tr><th>connector</th><th>status</th><th>started</th>
<th>fetched</th><th>new</th><th>dup</th><th>cost</th></tr>{run_rows}</table></section>"""
    return page("Sources", body, "sources")


async def source_add(request: Request):
    form = await request.form()
    kind, value = form.get("kind"), (form.get("value") or "").strip()
    if kind in SOURCE_KINDS and value:
        await db.execute("""insert into sources (kind, value, added_by) values (%s, %s, 'web')
                            on conflict (kind, value) do update set enabled = true""", kind, value)
    return RedirectResponse("/sources", status_code=303)


async def source_toggle(request: Request):
    await db.execute("update sources set enabled = not enabled where id = %s", int(request.path_params["id"]))
    return RedirectResponse("/sources", status_code=303)


async def source_run(request: Request):
    src = await db.fetchrow("select kind, value from sources where id = %s", int(request.path_params["id"]))
    if src and (conn := KIND_CONNECTOR.get(src["kind"])):
        task = asyncio.create_task(run_connector(conn, only_value=src["value"]))
        _running.add(task)
        task.add_done_callback(_running.discard)
    return RedirectResponse("/sources", status_code=303)


# ---------------------------------------------------------------- JSON API (same filters as the page)
async def api_search(request: Request):
    p = request.query_params
    results = await s.search(query=p.get("q"), author=p.get("author"), org=p.get("org"), topic=p.get("topic"),
                             type=p.get("type"), source=p.get("source"), since=p.get("since"),
                             min_relevance=float(p["min_relevance"]) if p.get("min_relevance") else None,
                             limit=int(p.get("limit", 20)))
    return Response(json.dumps(results, default=str), media_type="application/json")


class BasicAuth(BaseHTTPMiddleware):
    """Only active when WEB_PASSWORD is set (any username)."""

    async def dispatch(self, request, call_next):
        pw = settings().web_password
        if pw:
            auth = request.headers.get("authorization", "")
            ok = False
            if auth.startswith("Basic "):
                try:
                    ok = secrets.compare_digest(base64.b64decode(auth[6:]).decode().split(":", 1)[1], pw)
                except Exception:  # malformed header
                    ok = False
            if not ok:
                return Response("login required", 401, {"WWW-Authenticate": 'Basic realm="scout"'})
        return await call_next(request)


@asynccontextmanager
async def lifespan(_app):
    yield
    await db.close()


app = Starlette(
    routes=[
        Route("/", home), Route("/item/{id:int}", item_page),
        Route("/item/{id:int}/curate", curate, methods=["POST"]),
        Route("/item/{id:int}/reenrich", reenrich_item, methods=["POST"]),
        Route("/item/{id:int}/delete", delete_item, methods=["POST"]),
        Route("/add", add_link, methods=["POST"]),
        Route("/authors", authors_page), Route("/author", author_page),
        Route("/sources", sources_page), Route("/sources/add", source_add, methods=["POST"]),
        Route("/sources/{id:int}/toggle", source_toggle, methods=["POST"]),
        Route("/sources/{id:int}/run", source_run, methods=["POST"]),
        Route("/api/search", api_search),
    ],
    middleware=[Middleware(BasicAuth)],
    lifespan=lifespan,
)


def run() -> None:
    import uvicorn

    cfg = settings()
    log.info("web.start", url=f"http://{cfg.web_host}:{cfg.web_port}")
    uvicorn.run(app, host=cfg.web_host, port=cfg.web_port, log_level="warning")
