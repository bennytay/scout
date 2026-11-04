"""Postgres access: one async pool + a tiny migration runner (plain SQL files, applied in order)."""
from pathlib import Path

from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import settings
from .log import log

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
_pool: AsyncConnectionPool | None = None


async def _configure(conn):
    await register_vector_async(conn)


async def pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            settings().database_url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row, "autocommit": True, "prepare_threshold": None},
            configure=_configure,
            open=False,
        )
        await _pool.open()
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def fetch(sql: str, *args) -> list[dict]:
    p = await pool()
    async with p.connection() as conn:
        cur = await conn.execute(sql, args or None)
        return await cur.fetchall() if cur.description else []


async def fetchrow(sql: str, *args) -> dict | None:
    rows = await fetch(sql, *args)
    return rows[0] if rows else None


async def execute(sql: str, *args) -> None:
    p = await pool()
    async with p.connection() as conn:
        await conn.execute(sql, args or None)


async def migrate(dsn: str | None = None) -> list[str]:
    """Apply pending migrations/*.sql. Uses its own connection (vector type may not exist yet)."""
    import psycopg

    applied: list[str] = []
    async with await psycopg.AsyncConnection.connect(dsn or settings().database_url, autocommit=True) as conn:
        await conn.execute(
            "create table if not exists schema_migrations (name text primary key, applied_at timestamptz default now())"
        )
        done = {r[0] for r in await (await conn.execute("select name from schema_migrations")).fetchall()}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            async with conn.transaction():
                await conn.execute(f.read_text())
                await conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))
            log.info("migration.applied", name=f.name)
            applied.append(f.name)
    return applied
