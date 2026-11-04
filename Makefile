.PHONY: setup db migrate seed test eval bot mcp mcp-http ingest

setup: db           ## one command: local Postgres, deps, schema, a week of data
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
