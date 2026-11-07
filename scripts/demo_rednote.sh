#!/usr/bin/env bash
# RedNote (小红书) demo: a fresh database, one RedNote scan, then searches over what was kept.
#
#   scripts/demo_rednote.sh            # against the bundled stand-in server + sample notes (no RedNote account)
#   REDNOTE_MCP_URL=http://localhost:18060 scripts/demo_rednote.sh --live   # against a real, logged-in
#                                      # xiaohongshu-mcp server (docs/rednote.md)
#
# Needs Postgres (make db) and ANTHROPIC_API_KEY for the English summaries (LLM_PROVIDER=fake works offline).
set -euo pipefail
cd "$(dirname "$0")/.."
ADMIN=${ADMIN_DATABASE_URL:-postgresql://scout:scout@localhost:54329/postgres}
export DATABASE_URL=${ADMIN%/*}/scout_rednote_demo
export REDNOTE_MCP_URL=${REDNOTE_MCP_URL:-http://127.0.0.1:18061}
export X_BEARER_TOKEN= X_API_KEY= X_API_SECRET=   # RedNote only

if [[ "${1:-}" != "--live" ]]; then
  uv run python scripts/xhs_stub.py --port "${REDNOTE_MCP_URL##*:}" & STUB=$!
  trap 'kill $STUB 2>/dev/null' EXIT
  sleep 2
fi

psql "$ADMIN" -qc "drop database if exists scout_rednote_demo with (force)" -c "create database scout_rednote_demo"
uv run scout migrate >/dev/null
uv run scout ingest --source rednote

for q in "dexterous bimanual manipulation" "VLA fine-tuning" "SLAM" "humanoid foundation model"; do
  echo; echo "── scout search --source rednote \"$q\""
  uv run scout search --source rednote --limit 3 "$q" | uv run python -c '
import json, sys
rows = json.load(sys.stdin)
for r in rows:
    print("  " + r["title"] + "\n    " + r.get("summary", "")[:160])
if not rows:
    print("  (nothing stored: gated or judged out)")'
done
