# Scout: a robotics news radar

- **X is the main source.** Every 2 hours Scout scans ~80 trusted robotics accounts plus open searches for posts that link to papers, code or big news.
- **RedNote (小红书) too.** Scout searches it for Chinese robotics research and stores each note with an English headline and summary ([setup](docs/rednote.md)).
- **Only the signal is kept.** Free rules drop spam and low-engagement posts; Claude drops promo, off-topic and noise. In testing, nothing kept was junk.
- **Every post is followed to its source.** The arXiv paper, GitHub repo or Hugging Face model it links to is stored alongside it.
- **One Postgres database** holds everything, searchable by meaning, keywords, author and topic.
- **Used from Discord:** a daily brief (or `/scan`), paste links to store them, `/topic`, `/author`, `/recent`, `/rednote`, `/scan_rednote`, and `@Scout` questions in plain English.
- **Used from any AI tool through MCP:** Claude, Cursor or your own agent can search the same database. No vendor lock-in.

## Run it

```bash
cp .env.example .env   # add ANTHROPIC_API_KEY, a Discord bot token + 2 channel IDs, optionally an X key
make setup && make bot
```

Full setup: Discord bot, MCP for Claude, Cursor and Claude Code, RedNote, troubleshooting: [docs/setup.md](docs/setup.md).

## Architecture

![Scout architecture: X and RedNote → ingest pipeline → Postgres → MCP server → any AI chat session, with the Discord bot on the same database](docs/diagrams/mcp.png)
