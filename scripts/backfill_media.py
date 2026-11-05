"""One-off: fill in post images and avatars (items.media) for X posts stored before migration 013.

    uv run python scripts/backfill_media.py

Uses the free fxtwitter API (no X credits). New posts get media straight from the X API.
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from psycopg.types.json import Jsonb  # noqa: E402

from scout import db  # noqa: E402
from scout.connectors import http_client  # noqa: E402
from scout.connectors.x import FX, fx_media  # noqa: E402


async def main():
    rows = await db.fetch("select id, canonical_url from items where type = 'post' and media = '{}'::jsonb")
    filled = 0
    async with http_client() as http:
        for r in rows:
            m = re.search(r"/status/(\d+)", r["canonical_url"])
            if not m:
                continue
            resp = await http.get(FX.format(id=m.group(1)))
            if resp.status_code == 200 and (t := resp.json().get("tweet")) and (media := fx_media(t)):
                await db.execute("update items set media = %s where id = %s", Jsonb(media), r["id"])
                filled += 1
    print(f"filled {filled} of {len(rows)} posts")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
