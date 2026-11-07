#!/usr/bin/env bash
# Try /scan_rednote in a real Discord server without a RedNote account.
#
# Starts the stand-in xiaohongshu-mcp server (14 sample notes), points the bot at it with a fresh database,
# and turns off scheduled scans and the daily brief, so nothing happens until you run /scan_rednote.
# Needs DISCORD_TOKEN (and channel ids) + ANTHROPIC_API_KEY in .env, and Postgres (make db).
#
#   scripts/rednote_bot_test.sh            # then in Discord: /scan_rednote, then /rednote bimanual
#   Run it again to reset: each start is a fresh database, so the sample notes are "new" again.
set -euo pipefail
cd "$(dirname "$0")/.."
ADMIN=${ADMIN_DATABASE_URL:-postgresql://scout:scout@localhost:54329/postgres}
export DATABASE_URL=${ADMIN%/*}/scout_rednote_test
export REDNOTE_MCP_URL=http://127.0.0.1:18061 REDNOTE_SCHEDULED=false DAILY_BRIEF=false
export X_BEARER_TOKEN= X_API_KEY= X_API_SECRET=   # RedNote only: no X credits spent while testing

uv run python scripts/xhs_stub.py --port 18061 & STUB=$!
trap 'kill $STUB 2>/dev/null' EXIT
psql "$ADMIN" -qc "drop database if exists scout_rednote_test with (force)" -c "create database scout_rednote_test"
echo "Stand-in RedNote server on :18061 with 14 sample notes. In Discord: /scan_rednote"
uv run scout bot
