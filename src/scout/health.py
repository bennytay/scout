"""Health check: failing sources, failed runs, ingestion stalls. Posts to Discord when unhealthy."""
import httpx

from . import db
from .config import settings


async def problems() -> list[str]:
    out = []
    for r in await db.fetch(
        """select kind, value, consecutive_failures, last_error from sources
           where enabled and consecutive_failures >= 3 order by consecutive_failures desc"""):
        out.append(f"source `{r['kind']}:{r['value']}` failed {r['consecutive_failures']}× in a row: "
                   f"{(r['last_error'] or '')[:150]}")
    for r in await db.fetch(
        """select distinct on (connector) connector, status, error, started_at from ingest_runs
           order by connector, started_at desc"""):
        if r["status"] == "failed":
            out.append(f"connector `{r['connector']}` last run failed: {(r['error'] or '')[:150]}")
    stale = await db.fetchrow("select max(ingested_at) < now() - interval '36 hours' as stale from items")
    if stale and stale["stale"]:
        out.append("no new items ingested in 36h. Is the cron running?")
    return out


async def notify(lines: list[str]) -> bool:
    """Post via webhook (works from GitHub Actions without the bot). Returns True if sent."""
    url = settings().discord_alerts_webhook_url
    if not url or not lines:
        return False
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.post(url, json={"content": "🩺 **Scout health check**\n" + "\n".join(f"• {l}" for l in lines)})
        return r.is_success
