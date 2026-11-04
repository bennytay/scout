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
        "Scout is Auki Labs' robotics research radar: papers, repos, posts, models and datasets from arXiv, "
        "GitHub, Hugging Face, X, Hacker News, alphaXiv, RSS and links the team shares in Discord. "
        "Use `search` for most questions (it is hybrid: keyword + semantic + fuzzy author/org names). "
        "Always cite items by their `url`. `auki_relevance` (0-1) says how much an item matters to Auki."
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
    source: arxiv | github | huggingface | x | hackernews | alphaxiv | rss | discord.
    since: ISO date or relative like "7d", "2w", "3m". min_relevance: 0-1 Auki relevance floor.
    """
    return await s.search(query=query, author=author, org=org, topic=topic, type=type, source=source,
                          since=since, min_relevance=min_relevance, limit=limit)


@mcp.tool()
async def get_item(id: int) -> dict:
    """Full detail for one item: summary, authors, orgs, topics, entities, metrics, feedback, related items."""
    return await s.get_item(id) or {"error": f"no item {id}"}


@mcp.tool()
async def find_related(id: int, limit: int = 8) -> list[dict]:
    """Items linked to this one (repo implements paper, post discusses paper) plus nearest neighbours."""
    return await s.find_related(id, limit)


@mcp.tool()
async def author_profile(name: str) -> dict:
    """What we know about a researcher: items, topics, frequent co-authors, orgs. Fuzzy name or @handle."""
    return await s.author_profile(name) or {"error": f"no author matching {name!r}"}


@mcp.tool()
async def trending(topic: str | None = None, days: int = 7, limit: int = 10) -> list[dict]:
    """What's getting attention: cross-source sightings, upvotes/stars/points, team 👍, Auki relevance."""
    return await s.trending(topic, days, limit)


@mcp.tool()
async def digest(days: int = 7) -> dict:
    """Structured digest of the last N days: counts by topic, most Auki-relevant items, trending items."""
    return await s.digest(days)


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
