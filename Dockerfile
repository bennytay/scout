# One image, two processes: the Discord bot and the MCP HTTP server (see Procfile / railway.json).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
CMD ["sh", "-c", "scout migrate && (scout mcp --http & scout bot)"]
