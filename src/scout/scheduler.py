"""Minimal in-process scheduler for running locally (the GitHub Actions cron does the same job when hosted).

Restart-safe: "is it due?" is decided from the last ingest_runs row, not from in-memory state.
"""
import asyncio

from . import db, health
from .connectors import REGISTRY
from .log import log
from .pipeline.run import run_connector

EVERY_HOURS = {"x": 8}  # X reads cost credits: 3x/day
DEFAULT_HOURS = 4


async def due(name: str) -> bool:
    hours = EVERY_HOURS.get(name, DEFAULT_HOURS)
    row = await db.fetchrow(
        """select count(*) = 0 as due from ingest_runs
           where connector = %s and started_at > now() - make_interval(hours => %s)""", name, hours)
    return row["due"]


async def loop(tick_seconds: int = 300) -> None:
    log.info("scheduler.start", connectors=list(REGISTRY))
    while True:
        for name in REGISTRY:
            try:
                if await due(name):
                    await run_connector(name)
            except Exception as e:  # never let one connector kill the scheduler
                log.error("scheduler.connector_crashed", connector=name, error=repr(e)[:300])
        if problems := await health.problems():
            log.warning("health.problems", problems=problems)
            await health.notify(problems)
        await asyncio.sleep(tick_seconds)
