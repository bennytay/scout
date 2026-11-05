.PHONY: setup db migrate test eval bot mcp mcp-http ingest demo

setup: db           ## local Postgres, deps, schema, a week of data (quiet: no Discord posts)
	uv sync
	@test -f .env || cp .env.example .env
	@sleep 3
	uv run scout migrate
	uv run scout ingest --days 7

db:
	docker compose up -d --wait

migrate:
	uv run scout migrate

ingest:
	uv run scout ingest

test:
	uv run pytest -q

eval:
	uv run python evals/run.py

bot:
	uv run scout bot

mcp:
	uv run scout mcp

mcp-http:
	uv run scout mcp --http

demo: db            ## separate fresh database, then the bot fills the Discord feed live from every source
	docker compose exec -T db psql -U scout -d postgres -qc "drop database if exists scout_demo with (force)" -c "create database scout_demo"
	DATABASE_URL=postgresql://scout:scout@localhost:54329/scout_demo LOOKBACK_DAYS=2 uv run scout migrate
	DATABASE_URL=postgresql://scout:scout@localhost:54329/scout_demo LOOKBACK_DAYS=2 uv run scout bot
