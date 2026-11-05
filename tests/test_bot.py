"""Bot logic that touches the database: /follow, /unfollow, radar suggestions (the learn step)."""
from scout.bot.main import brief_due, follow, radar_suggestion, scan_line
from scout.pipeline.run import RunStats


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


def test_scan_line():
    st = RunStats(fetched=212, gated=170, dropped=28, inserted=14, expanded=6)
    assert scan_line(st, True) == ("📡 Scanned X: 212 posts → 42 passed the filter → **14 kept** "
                                   "(+6 papers/repos they link to)")
    assert scan_line(None, False) == "📡 Scanning X ⏳"


async def test_brief_cadence(database):
    assert not await brief_due(6)  # nothing stored yet
    await database.execute("insert into items (canonical_url, type, title, source) values ('https://x.com/a/status/1', 'post', 't', 'x')")
    assert await brief_due(6)
    await database.execute("insert into briefs (window_start, window_end, n_candidates, n_new_items, model, cost_usd, stories, sources) "
                           "values (now() - interval '1 day', now(), 1, 1, 'm', 0, '[]', '{}')")
    assert not await brief_due(6)  # just posted one
