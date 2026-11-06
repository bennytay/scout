#!/bin/sh
# Make the next /scan show a full brief again (for recording a demo): moves past briefs into briefs_archive.
# Nothing else changes: stored items, X scan cursors and the radar stay as they are.
# Run the bot with DAILY_BRIEF=false while recording, or it posts its own brief once there are none.
set -e
docker exec -i scout-db-1 psql -U scout -d "${1:-scout_demo}" -q -v ON_ERROR_STOP=1 <<'SQL'
begin;
create table if not exists briefs_archive as select * from briefs with no data;
insert into briefs_archive select * from briefs;
delete from briefs;
commit;
SQL
echo "Briefs archived. The next /scan covers everything stored in the last 2 days."
