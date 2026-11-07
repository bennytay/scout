"""MCP server: any MCP client (Claude Desktop, Cursor, Claude Code...) can query the radar.

stdio:  scout mcp
HTTP:   scout mcp --http   (streamable HTTP at /mcp, requires `Authorization: Bearer $MCP_BEARER_TOKEN`)
Every result includes `url` so answers can cite sources.
"""
from typing import Literal

from mcp.server.mcpserver import MCPServer

from . import search as s
from .pipeline.run import ingest_url

mcp = MCPServer(
    "scout",
    instructions=(
        "Scout is a general robotics news radar (built for Auki Labs). X (and RedNote / 小红书, for Chinese robotics research) is the newsroom: high-signal robotics posts, plus the papers, "
        "repos, models and datasets they link to, plus links the team shares in Discord. "
        "Use `search` for everything: free text (hybrid keyword + semantic) and/or structured fields. "
        "To look up a person, lab or topic, fill `author`, `org` or `topic` instead of putting names in `query`. "
        "Always cite items by their `url`. `importance` (0-1) is general significance for robotics; "
        "`auki_relevance` (0-1) is how much it matters to Auki specifically (secondary)."
    ),
)

ItemTypeArg = Literal["paper", "repo", "post", "article", "model", "dataset", "video"]


@mcp.tool()
async def search(query: str | None = None, author: str | None = None, org: str | None = None,
                 topic: str | None = None, type: ItemTypeArg | None = None, source: str | None = None,
                 since: str | None = None, min_relevance: float | None = None, limit: int = 10) -> list[dict]:
    """Hybrid search over the database.

    query: free text (optional if filtering). author/org: fuzzy names, e.g. "Levine", "DeepMind".
    topic: manipulation | locomotion | humanoids | vla-foundation-models | sim2real | slam-spatial-mapping |
           perception | hardware | datasets-benchmarks | multi-agent | other (synonyms like "SLAM" work).
    source: x | rednote | discord | arxiv | github | huggingface (the last three: things posts linked to).
            rednote = 小红书 notes (Chinese, stored with English summaries; search them in English).
    since: ISO date or relative like "7d", "2w", "3m". min_relevance: 0-1 Auki relevance floor.
    """
    return await s.search(query=query, author=author, org=org, topic=topic, type=type, source=source,
                          since=since, min_relevance=min_relevance, limit=limit)


@mcp.tool()
async def get_item(id: int) -> dict:
    """Full detail for one item: summary, authors, orgs, topics, entities, metrics, and related items
    (the paper an X post discusses, the repo implementing a paper, nearest neighbours)."""
    return await s.get_item(id) or {"error": f"no item {id}"}


@mcp.tool()
async def latest_brief() -> dict:
    """The most recent news brief: top 7-10 stories (X-first), each with links to paper/code/model."""
    from .brief import latest

    rows = await latest(1)
    return dict(rows[0]) if rows else {"error": "no brief yet"}


@mcp.tool()
async def add_link(url: str, note: str | None = None) -> dict:
    """Ingest a URL now (paper, repo, X post, article...). Returns the stored item with its enrichment."""
    r = await ingest_url(url, submitted_by="mcp")
    if not r.item_id:
        return {"status": r.status, "error": r.error}
    return {"status": r.status, "item": await s.get_item(r.item_id), "note": note}


def run_stdio() -> None:
    mcp.run(transport="stdio")


def http_app():
    """Streamable HTTP app wrapped in bearer-token auth."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    from .config import settings

    token = settings().mcp_bearer_token
    if not token:
        raise SystemExit("MCP_BEARER_TOKEN must be set for HTTP transport")

    class BearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path == "/health":
                return JSONResponse({"ok": True})
            if request.headers.get("authorization") != f"Bearer {token}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    from mcp.server.transport_security import TransportSecuritySettings

    # DNS-rebinding protection targets browser→localhost attacks; this is a token-protected remote service.
    app = mcp.streamable_http_app(
        host=settings().mcp_host,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    app.add_middleware(BearerAuth)
    return app


def run_http() -> None:
    import uvicorn

    from .config import settings

    uvicorn.run(http_app(), host=settings().mcp_host, port=settings().mcp_port)
