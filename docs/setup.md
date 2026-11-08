# Setting up Scout

About 15 minutes. Everything runs on your machine: Postgres in Docker, embeddings on the CPU.

## 1. Install

You need [Docker](https://www.docker.com/) and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/bennytay/scout && cd scout
cp .env.example .env
```

## 2. Keys (in `.env`)

| Key | Needed? | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | [console.anthropic.com](https://console.anthropic.com) |
| `DISCORD_TOKEN`, `DISCORD_LINKS_CHANNEL_ID`, `DISCORD_FEED_CHANNEL_ID` | For the bot | Step 3 |
| `X_API_KEY` + `X_API_SECRET` | Optional | [developer.x.com](https://developer.x.com), app consumer key and secret. Without them X isn't scanned, but pasted X links still work. |
| `REDNOTE_MCP_URL` | Optional | Step 6 |

`.env` is gitignored. Never commit it.

## 3. Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications), then **New Application**.
2. Under **Bot**, click **Reset Token** and copy the token into `DISCORD_TOKEN`. On the same page, turn on **Message Content Intent**. Without it, the bot can't read pasted links or `@Scout` questions.
3. Under **OAuth2 → URL Generator**, tick the scopes `bot` and `applications.commands`. Then tick the permissions View Channels, Send Messages, Embed Links and Read Message History. Open the generated URL and add the bot to your server.
4. Create two channels, one for links and one for the feed (e.g. `#links` and `#alerts`). In Discord, turn on **Settings → Advanced → Developer Mode**, then right-click each channel → **Copy Channel ID** and paste the IDs into `DISCORD_LINKS_CHANNEL_ID` and `DISCORD_FEED_CHANNEL_ID`.

## 4. Run

```bash
make setup   # Postgres + pgvector in Docker, schema, and a week of X posts (if you set an X key)
make bot     # leave it running
```

To check it works:
- The bot shows as online.
- Typing `/` in your server lists `/scan`, `/topic`, `/author`, `/recent`, `/rednote` and `/scan_rednote`. They sync to each server as soon as the bot starts.
- Paste an arXiv or X link in the links channel and the bot replies with a card.
- `@Scout what's new in humanoids?` answers in plain English.

The bot scans X every 2 hours and posts a brief at 9am (`BRIEF_HOUR` and `BRIEF_TZ`). `/scan` does both now.

## 5. MCP (use Scout from Claude, Cursor or your own agent)

Scout's MCP server has four tools: `search`, `get_item`, `latest_brief` and `add_link`. Postgres must be running (`make db`), and the bot doesn't need to be. Use absolute paths, and find yours with `which uv` and `pwd`.

**Claude Desktop:** in Settings → Developer → Edit Config, add this to `claude_desktop_config.json`, then restart Claude:

```json
{
  "mcpServers": {
    "scout": {
      "command": "/absolute/path/to/uv",
      "args": ["--directory", "/absolute/path/to/scout", "run", "scout", "mcp"]
    }
  }
}
```

**Cursor:** put the same `mcpServers` block in `~/.cursor/mcp.json`.

**Claude Code:**

```bash
claude mcp add scout -- uv --directory /absolute/path/to/scout run scout mcp
```

**Remote clients (e.g. ChatGPT connectors, hosted agents):** set `MCP_BEARER_TOKEN` in `.env` and run `make mcp-http`. This serves `http://localhost:8765/mcp` and requires `Authorization: Bearer <token>`. Put it behind a public HTTPS URL (a tunnel or a host) for clients that aren't on your machine.

To test it, ask Claude "Use Scout to find recent humanoid robot papers".

## 6. RedNote (optional)

See [rednote.md](rednote.md). It needs a dedicated RedNote account logged in to a self-hosted xiaohongshu-mcp server. On Apple Silicon Macs, use the project's native `darwin-arm64` build and login tool rather than the Docker image. Search on RedNote's website can be rate-limited for new accounts.

To try it without an account, run `make rednote-bot-test`. This starts the bot on 14 sample notes, so `/scan_rednote` works.

## 7. Look inside the database

Connect any Postgres client to `postgresql://scout:scout@localhost:54329/scout`, or run `docker compose exec db psql -U scout -d scout`. [queries.sql](queries.sql) has ten ready-made queries.

## Troubleshooting

- **The bot crashes with `PrivilegedIntentsRequired`:** turn on Message Content Intent (step 3).
- **No slash commands:** the bot was added without the `applications.commands` scope. Re-invite it with the URL from step 3.
- **The feed is empty:** without an X key, nothing is scanned. Paste links, or add a key and run `/scan`.
- **Claude doesn't show Scout:** check that the paths in the config are absolute and that `make db` is running, then fully restart Claude.
- **Tests:** `make test`.
