"""Bot logic that touches the database: /follow, /unfollow, radar suggestions (the learn step)."""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from scout.bot.main import brief_cutoff, brief_due, follow, radar_suggestion


async def test_follow_and_unfollow_edit_the_radar(database):
    assert "on the radar" in await follow("@NewLab", True)
    row = await database.fetchrow("select enabled from sources where kind = 'x_account' and value = 'NewLab'")
    assert row["enabled"]
    assert "removed" in await follow("newlab", False)
    assert "doesn't look like" in await follow("not a handle!", True)
    assert "wasn't on the radar" in await follow("nobody_here", False)


async def test_radar_suggestion_once_per_account(database):
    await database.execute("insert into x_accounts (handle, judged, kept) values ('goodposter', 4, 3), "
                           "('noisy', 10, 3), ('svlevine', 9, 9)")
    msg = await radar_suggestion()
    assert "@goodposter" in msg and "3 of 4" in msg and "/follow goodposter" in msg
    assert await radar_suggestion() is None  # noisy: kept rate too low; svlevine: already on the radar


def test_brief_cutoff_is_the_last_9am_sydney():
    syd = ZoneInfo("Australia/Sydney")
    assert brief_cutoff(datetime(2026, 11, 5, 10, 0, tzinfo=syd), 9, "Australia/Sydney") == datetime(2026, 11, 5, 9, tzinfo=syd)
    assert brief_cutoff(datetime(2026, 11, 5, 8, 0, tzinfo=syd), 9, "Australia/Sydney") == datetime(2026, 11, 4, 9, tzinfo=syd)
    assert brief_cutoff(datetime(2026, 11, 4, 23, 0, tzinfo=UTC), 9, "Australia/Sydney").hour == 9


async def test_brief_is_daily(database):
    tz = "Australia/Sydney"
    assert not await brief_due(9, tz)  # nothing stored yet
    await database.execute("insert into items (canonical_url, type, title, source) values ('https://x.com/a/status/1', 'post', 't', 'x')")
    assert await brief_due(9, tz)
    await database.execute("insert into briefs (window_start, window_end, n_candidates, n_new_items, model, cost_usd, stories, sources) "
                           "values (now() - interval '1 day', now(), 1, 1, 'm', 0, '[]', '{}')")
    assert not await brief_due(9, tz)  # one already posted since today's 9am
