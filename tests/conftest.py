import os
from pathlib import Path

import psycopg
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
ADMIN_DSN = os.environ.get("TEST_ADMIN_DATABASE_URL", "postgresql://scout:scout@localhost:54329/postgres")
TEST_DSN = ADMIN_DSN.rsplit("/", 1)[0] + "/scout_test"

os.environ.update({"LLM_PROVIDER": "fake", "EMBEDDING_PROVIDER": "fake", "DATABASE_URL": TEST_DSN,
                   "X_BEARER_TOKEN": "test-token", "X_MAX_RESULTS": "100", "GITHUB_TOKEN": ""})


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _db_available() -> bool:
    try:
        psycopg.connect(ADMIN_DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


@pytest.fixture
async def database():
    """Fresh database with all migrations applied, per test."""
    if not _db_available():
        pytest.skip("Postgres not available (run `docker compose up -d`)")
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        c.execute("drop database if exists scout_test with (force)")
        c.execute("create database scout_test")
    from scout import db
    from scout.config import settings

    settings.cache_clear()
    await db.close()
    await db.migrate(TEST_DSN)
    yield db
    await db.close()
