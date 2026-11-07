# RedNote (小红书) in Scout

Scout scans RedNote for robotics research the same way it scans X. It runs keyword searches, applies a free spam
and engagement gate, and opens only the notes that pass. Claude then judges each note and writes an English
headline and summary, and Scout follows any arXiv or GitHub links in the note. Kept notes show up in `search`
(`source=rednote`), `/rednote`, `@Scout`, MCP and the daily brief.

```
xiaohongshu-mcp (Docker, logged-in RedNote session in a headless browser)
   │  POST /api/v1/feeds/search   {"keyword": "具身智能 论文", "filters": {"sort_by": "综合", "publish_time": "一周内"}}
   │  POST /api/v1/feeds/detail   {"feed_id", "xsec_token"}
   ▼
scout ingest --source rednote ─► gate (spam lexicon, ≥20 likes, per-author cap, copies, already seen)
   ─► detail (≤30/scan) ─► Claude: English summary + title_en + signal (promo/off_topic/noise dropped)
   ─► Postgres ─► follow arXiv / GitHub links ─► search, /rednote, MCP, brief
```

## Set up (about 10 minutes)

1. Run [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) next to Scout. Use a
   **dedicated RedNote account**, not a personal one:
   ```bash
   mkdir xhs && cd xhs && curl -O https://raw.githubusercontent.com/xpzouying/xiaohongshu-mcp/main/docker/docker-compose.yml
   docker compose up -d          # image xpzouying/xiaohongshu-mcp, port 18060, cookies in ./data
   ```
2. Log in once. Fetch the QR code from `GET http://localhost:18060/api/v1/login/qrcode` (the `img` field is a
   base64 PNG) or use the project's login tool, then scan it with the RedNote app. Check the login with
   `curl localhost:18060/api/v1/login/status`, which should return `"is_logged_in": true`. Cookies persist in
   `./data`, so log in again only when they expire. Don't open the same account in another web browser, because
   that logs out the server's session.
3. Point Scout at the server in `.env`:
   ```
   REDNOTE_MCP_URL=http://localhost:18060
   REDNOTE_MCP_TOKEN=            # only if you started the server with AUTH_TOKEN
   ```
4. Run `scout migrate` (seeds 10 searches), then `scout ingest --source rednote`. The bot then scans every
   `REDNOTE_EVERY_HOURS` (default 6) and `/scan` includes RedNote.

The same server is also an MCP server (`http://localhost:18060/mcp`), so Claude Desktop or Claude Code can browse
RedNote directly next to Scout's own MCP.

## Tuning

| Setting | Default | What it does |
|---|---|---|
| `rednote_query` rows in `sources` | 10 seeded | Searches. Pair a robotics term with a research word (`论文`, `arxiv`, `开源`), or results drift to shopping. |
| `REDNOTE_SORT` | `综合` | 综合 (relevance), 最新, 最多点赞, 最多评论, 最多收藏 |
| `REDNOTE_PUBLISH_TIME` | `一周内` | 不限, 一天内, 一周内, 半年内 |
| `REDNOTE_MIN_LIKES` | 20 | Gate: likes on the card |
| `REDNOTE_MAX_DETAILS` | 30 | Notes opened per scan (the slow, account-visible step). Cards over the cap are retried next scan. |
| `REDNOTE_MAX_PER_AUTHOR` | 3 | Per scan |

Add a search with `insert into sources (kind, value) values ('rednote_query', '触觉传感 论文');`.

## Try it without a RedNote account

```bash
make db && make rednote-demo
```

This command starts `scripts/xhs_stub.py`, a stand-in that speaks xiaohongshu-mcp's exact REST API and serves the
14 **sample** notes in `demo/rednote_sample_notes.json`. The sample notes were written for the demo: the accounts
are fictional, but the papers and links are real. It then runs a real scan into a fresh `scout_rednote_demo`
database and searches the results. The tests (`tests/test_rednote.py`) use the same stand-in.

## Limits

- Search returns one page of results per query (no scrolling), so the volume comes from more queries, not deeper
  pages.
- Search cards have no body text or date, so the gate can only check title, poster and likes. The detail step
  fills in the rest.
- Chinese text is stored as-is in `full_text`, but keyword search runs on English (titles and summaries are
  English). Search in English.
- Note links need the viewer token, so Scout stores an openable link (`media.link`) next to the canonical URL.
- Scraping RedNote may conflict with its terms of service. This setup reads public notes at a low rate from one
  account. Decide whether that is acceptable for your use.
