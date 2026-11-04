# Scout: a robotics research radar for Auki Labs

Scout watches the sources that matter for robotics (arXiv, GitHub, Hugging Face, X, Hacker News, alphaXiv,
RSS) and **the links the team drops in one Discord channel**. It keeps a database of papers, repos, posts,
models and datasets that you can search by **author, org, topic and meaning**, and it reports in three places:

- **Discord, passive**: after each monitoring cycle the bot posts a **news brief**, the top 7–10 stories of the
  period, written by an editor model that treats X as the newsroom and links each story to its paper, code and
  model. Team-shared links get a 4-bullet reply.
- **Web UI, direct**: `make web` opens a search-and-maintain interface with facets for author, org, topic, type,
  source, date and Auki relevance, plus author pages, item pages, curation and source management. No LLM needed.
- **Any LLM, conversational**: through MCP, ask Claude Desktop, Cursor or Claude Code anything about the data.
  Answers cite links.

```mermaid
flowchart LR
  subgraph Sources
    A[arXiv cs.RO + filtered cs.CV/LG]
    G[GitHub orgs / releases / search]
    H[HF daily papers / models / datasets]
    X[X API v2 accounts + search]
    N[Hacker News]
    AX[alphaXiv hot]
    R[RSS]
    D[Discord links channel]
  end
  subgraph Pipeline
    C[canonicalise URL] --> DD[dedupe: url → arXiv id → DOI → embedding]
    DD --> E[enrich: LLM structured output<br/>summary · topics · authors/orgs · entities · Auki relevance]
    E --> EM[embed locally<br/>bge-small, CPU] --> U[upsert + sightings] --> L[link paper ↔ repo ↔ post]
  end
  A & G & H & X & N & AX & R -->|bot's monitor loop / cron| C
  D -->|priority| C
  U --> PG[(Postgres<br/>pgvector + pg_trgm + tsvector)]
  PG --> S[hybrid search<br/>RRF of FTS + vector + fuzzy names]
  S --> MCP[MCP server<br/>stdio + HTTP/bearer]
  PG --> BR[news brief<br/>editor LLM: cluster · X-first · top 7-10]
  BR --> BOT[Discord bot<br/>brief + link replies]
  S --> WEB[web UI<br/>search · facets · curate]
```

## Quick start (one command)

Runs entirely on your machine: Postgres in docker, embeddings on CPU, Claude for enrichment.

```bash
cp .env.example .env   # add ANTHROPIC_API_KEY (X_BEARER_TOKEN, GITHUB_TOKEN, DISCORD_* optional)
make setup             # local Postgres (docker), deps, schema, 7-day backfill
make bot               # monitor every source + post the news brief to Discord
make web               # search + maintain the database at http://127.0.0.1:8000
```

**For a live demo:** `make demo` starts the bot on a fresh, separate demo database (your main one is untouched),
so the feed channel fills up source by source in front of you.

No keys yet? `LLM_PROVIDER=fake EMBEDDING_PROVIDER=fake make setup` runs the whole system offline with
deterministic heuristics, so tests, evals and demos work with zero credentials.

Then:

```bash
uv run scout search "visual relocalization" --since 7d
uv run scout ask "who is working on multi-robot shared maps?"
uv run scout add https://arxiv.org/abs/2611.05084        # ingest any URL now
make bot                                                # Discord bot
make mcp                                                # MCP over stdio
```

**Hosting later?** Any Postgres with pgvector works. Point `DATABASE_URL` at Supabase/Neon/RDS and run
`uv run scout migrate`. `.github/workflows/ingest.yml` is the hosted replacement for `scout scheduler`, and the
Dockerfile runs the bot and the MCP HTTP server together.

## Use it from an LLM client (MCP)

**Claude Desktop** (`claude_desktop_config.json`), local stdio:
```json
{
  "mcpServers": {
    "scout": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/scout", "run", "scout", "mcp"]
    }
  }
}
```

**Cursor** (`.cursor/mcp.json`), hosted HTTP:
```json
{
  "mcpServers": {
    "scout": {
      "url": "https://<your-host>/mcp",
      "headers": { "Authorization": "Bearer <MCP_BEARER_TOKEN>" }
    }
  }
}
```

**Claude Code**:
```bash
claude mcp add --transport http scout https://<your-host>/mcp --header "Authorization: Bearer $MCP_BEARER_TOKEN"
```

| Tool | What it does |
|---|---|
| `search(query?, author?, org?, topic?, type?, source?, since?, min_relevance?, limit?)` | Hybrid search. Fuzzy, typo-tolerant author/org names (`"levine"`, `"eth zürich"`), relative dates (`"7d"`). |
| `get_item(id)` | Full record: summary, entities, metrics, related items |
| `find_related(id)` | Explicit links (repo *implements* paper, post *discusses* paper) + nearest neighbours |
| `author_profile(name)` | Items, topics, frequent co-authors, orgs |
| `trending(topic?, days?)` | Cross-source sightings + upvotes/stars/points/likes + Auki relevance |
| `digest(days?)` | Counts by topic, most Auki-relevant, trending |
| `latest_brief()` | The latest news brief: top stories with their links |
| `add_link(url, note?)` | Ingest a URL now |

Every result carries `url`, so answers can cite sources.

## Discord

The bot does two things, and nothing else.

**1. Monitoring → news brief** (`DISCORD_FEED_CHANNEL_ID`). Each cycle (X 3×/day to save credits, everything
else every 4h), one status line updates in place while sources are scanned:

```
📡 Scanned: alphaXiv ✓ 33 · arXiv ✓ 56 · GitHub ✓ 1 · Hacker News ✓ 1 · Hugging Face ✓ 52 · RSS ✓ 2 → 145 new
```

Then the brief (a real one, trimmed to 3 of its 10 stories). An editor model (Claude Opus 5.5) clusters everything new into stories. X posts are the primary
source whenever one covers a story, and the supporting paper, code and model are linked:

```
📰 Robotics brief · Wed 04 Nov, 14:35 UTC · 701 new items → 10 stories

1. Tutor Intelligence raises $75M Series B led by Andreessen Horowitz
MIT CSAIL spin-out now has $117M total, signaling strong investor appetite for deployed warehouse robotics.
𝕏 @lukas_m_ziegler

5. Sparse anchors register robot sessions to maps despite scene changes 🔥
Multi-session visual registration in changing environments is core to persistent shared maps and relocalization.
paper: Sparse Anchors · paper: Spade-SLAM

6. New feed-forward camera localization methods generalize across cameras and maps 🔥
Ray-SCR and PGGT-Loc advance visual positioning across camera models and lightweight primitive-based maps.
paper: Ray-SCR · paper: PGGT-Loc · paper: PadLoc · paper: Beyond Local Refinement

📡 Monitored: arXiv 538 · Hugging Face 101 · alphaXiv 48 · Hacker News 36 · RSS 16 · GitHub 11 · X (team links only)
```

Every label is a link. The editor can only cite items from its candidate list, and URLs come from the
database, so it can't invent a link. A brief costs about $0.065. Preview one any time with
`scout brief --hours 24 --dry-run`.

**2. Team links** (`DISCORD_LINKS_CHANNEL_ID`). Post any link (paper, repo, X post, article) and get:

```
📄 LoD-Loc v4: Towards Generalized Aerial Visual Localization… · relevance 0.85
• What: An aerial visual localization method that registers a query image against a Panoptic LoD 3D map.
• Why Auki: Visual positioning against a shared 3D map is the relocalization problem the posemesh solves.
• Topics: slam-spatial-mapping, perception · Who: Shuaibang Peng, Chengming Zhang, Juelin Zhu et al.
• Related: Beyond Local Refinement: Wide-Area Precise…, PGGT-Loc: Primitive-Grounded Geometry…
```

## Web UI: search and maintain the database directly

`make web` → http://127.0.0.1:8000 (local only; set `WEB_PASSWORD` before exposing it).

| Page | What you can do |
|---|---|
| **Brief** | The latest news briefs. Every link opens the source, and ↪ opens the item in Scout |
| **Search** | Hybrid search box (meaning + keyword + fuzzy names); quoted phrases and `-exclusions` work. Clickable facets: topic, type, source, top orgs, top authors; filters for date and Auki relevance; sort by newest or relevance. Off-topic items are hidden by default |
| **Item** | Summary, why it matters, authors, orgs, topics, extracted entities (robots, datasets, methods, all clickable), related items, full text. **Maintain:** fix topics or relevance (recorded as *curated*, so later re-enrichment never overwrites a human decision), re-run enrichment, delete |
| **Authors** | Typo-tolerant author search; author pages with topics, co-authors, orgs and all their work |
| **Sources & health** | Add, disable or **run now** any tracked source; per-source health, last runs, and LLM spend |
| `/api/search` | The same search as JSON |

**Context search.** "robots sharing a map of a building" finds collaborative-SLAM papers with no words in common,
via the vector ranker. Entities extracted by the LLM (e.g. "GR00T", "Unitree G1") are indexed too. Paper
search covers abstracts, not full PDFs (see Known limits).

Power users can also connect any Postgres GUI (TablePlus, pgAdmin) with `DATABASE_URL`.

## Example questions with real answers

→ **[docs/examples.md](docs/examples.md)**, generated by `scripts/examples.py` against the live database
(regenerate any time, so it's never stale).

## Evals

A hand-labelled set: **56 recent real arXiv papers** (topics + Auki-relevance band) and **21 search queries
+ 5 author queries** with relevant sets (`evals/*.jsonl`). `make eval` loads them into a throwaway DB through
the real pipeline and scores them.

| Metric | Keyword heuristic (no LLM) | **Claude Haiku 5.5** |
|---|---|---|
| Topic: primary topic correct | 46% | **88%** |
| Topic: any expected topic predicted | 70% | **98%** |
| Topic: micro-F1 over topic sets | 50% | **78%** (P 69%, R 90%) |
| Auki relevance: band accuracy (high/mid/low) | 38% | **77%** |
| Search: precision@5 (capped at #relevant) | 0.85 | **0.87** |
| Search: MRR / hit@1 | 1.00 / 1.00 | 1.00 / 1.00 |
| Author filter: precision / recall | 87% / 100% | 87% / 100% |
| Enrichment cost for 56 items | $0 | **$0.038** (~$0.0007/item) |

Both columns use the same local embedder (bge-small), so search differs only through the LLM's summaries.
LLM outputs vary between runs: two runs a day apart scored 91%/88% primary topic and 75%/77% relevance band,
so read every number as ±3 points.

**What the errors look like.** Every relevance miss is off by one band, and none confuse *high* with *low*.
The model is generous: 7 of the 15 papers I labelled *low* (peripheral robotics, e.g. a robot-tutoring HRI study)
got 0.40–0.50, just over the *mid* cut-off. Topic precision (69%) is lower than recall (90%) because the model
often adds a reasonable second or third topic that the labels don't have. I deliberately did **not** tune the
prompt against these 56 items, since that would be fitting to the test set. The fix is more labelled data and
a held-out split.

Full breakdown, confusion matrix and per-query scores: [`evals/results.md`](evals/results.md).
Search is measured with the real local embedder (no LLM involved). The tagging and relevance column needs
`ANTHROPIC_API_KEY`. CI runs a fully offline variant (hash embeddings, P@5 0.72) as a regression guard.

## Cost estimate (monthly)

Assumes roughly 250 new items/day (~7.5k/month) after dedupe.

| | Assumption | $/month |
|---|---|---|
| Enrichment (Claude Haiku 5.5) | measured $0.0007/item on the eval run | ~$5 |
| Embeddings | local bge-small on CPU (~25 ms/item) | $0 |
| News brief (Claude Opus 5.5) | ~$0.065/brief × 6 cycles/day | ~$12 |
| Questions via MCP | the client's LLM does the reasoning; Scout only runs search | $0 |
| X API v2 (pay-per-use) | 5 seeded accounts + 2 queries, 3 runs/day, ≤20 new posts each, incremental via `since_id` | ≤ 12.6k post reads/month at the cap (usually far fewer) × X's current per-read price |
| Postgres | local docker (hosted later: Supabase/Neon free tiers cover months) | $0 |
| Bot + MCP host | local for the demo (hosted: a ~$5 container) | $0 |
| Cron | GitHub Actions, public repo | $0 |
| **Total** | | **~$17/mo of Claude + your X credits** (set `BRIEF_MODEL=claude-sonnet-5-5` to halve the brief cost) |

Real per-item cost is recorded in `items.cost_usd` and per run in `ingest_runs.cost_usd`. The bot shows the
cost of each ingestion in its reply.

## How to add a source (~30 lines)

`src/scout/connectors/rss.py` is the template:

```python
@register
class MySource(Connector):
    name = "mysource"
    kinds = ("mysource_feed",)          # rows in the `sources` table this connector consumes
    needs = ("mysource_api_key",)       # optional: skipped (not failed) when unset

    async def fetch(self, http, kind, value, since):
        r = await http.get("https://api.example.com/items", params={"q": value})
        r.raise_for_status()
        return [Item(url=x["url"], type=guess_type(x["url"]), title=x["title"], source=self.name,
                     summary=x.get("abstract"), published_at=parse(x["date"]))
                for x in r.json()["items"]]
```

Then: import it in `connectors/__init__.py`, add the kind to the `sources.kind` check constraint (a new
migration), insert a `sources` row, add it to the matrix in `.github/workflows/ingest.yml`, and record one real
response under `tests/fixtures/` for a test. Canonicalisation, dedupe, enrichment, linking, retries, error
isolation and logging come for free.

## Design notes

The full reasoning is in [DECISIONS.md](DECISIONS.md). The highlights:

- **One SQL function does hybrid search** (FTS + vector + trigram, reciprocal rank fusion), and every hit says
  why it matched.
- **Dedupe is a ladder**: URL → arXiv ID → DOI → embedding similarity. Similarity applies to posts and
  articles only, because two different papers from one lab can look 0.93-similar.
- **Nothing is overwritten.** Each source's sighting is kept, and that cross-source buzz is the trending signal.
- **Links resolve in either order**: a repo ingested before its paper still gets linked.
- **What matters to Auki is a prompt file** ([`prompts/auki_context.md`](prompts/auki_context.md)), so the
  team can edit it without a deploy.
- **Idempotent and isolated.** Re-running is safe, one bad item or feed never stops a run, and connectors
  without credentials are skipped rather than failed.

## Known limits

- **X monitoring needs X API credits.** The connector is tested against a synthetic fixture in the documented v2
  response format until a recorded response replaces it. X links shared in Discord work without any key.
- **alphaXiv** uses an unofficial API and may break. It fails soft.
- **Author disambiguation is name-based** (normalised and fuzzy). Two "Wei Zhang"s collapse into one; ORCID or
  Semantic Scholar IDs would fix this.
- **PDF full text isn't extracted.** Papers are enriched from title and abstract, which is enough for tagging but
  not for deep Q&A.
- **Eval labels** were drafted by the AI pair-programmer and are pending a human review pass (`evals/items.jsonl`).
  56 items is a small set, so read the numbers as directional.
- **Exact vector scan** in filtered search is fine up to ~100k items. Beyond that, see DECISIONS D3.

## Roadmap: towards a shared team memory

1. **Exocortex**: ingest the team's own artifacts (Discord threads, meeting notes, internal docs) next to the
   external ones, with the same search and the same MCP. "What did we conclude about Gaussian-splat maps last
   month, and what's new since?"
2. **People and lab graph**: resolve authors to ORCID/Semantic Scholar/GitHub; follow people, not just feeds;
   alert when someone in Auki's orbit publishes.
3. **Watch questions**: standing queries ("anything beating our relocalization latency?") that fire alerts with
   an LLM judge instead of a threshold.
4. **Full-text RAG over PDFs** with section-level chunks, for questions like "which method did they compare against?".
5. **Feedback loop**: 👍/👎 on feed items to tune ranking and propose edits to `auki_context.md` (removed
   from v1 to keep the bot focused).
6. **Weekly digest + draft posts** in Auki's voice for human approval (also cut from v1 for focus).

## Repo map

```
migrations/        SQL schema, hybrid search function, seed taxonomy + sources
prompts/           enrichment prompt, Auki relevance rubric, Auki voice for drafts
src/scout/
  connectors/      arxiv, github, huggingface, x, hackernews, alphaxiv, rss, resolve (any URL → Item)
  pipeline/        run (orchestration), dedupe, enrich, store, link
  providers/       llm (anthropic | openai | fake), embeddings (openai | fake)
  search.py        hybrid search, related, author profiles, trending, digest, /ask
  mcp_server.py    7 MCP tools, stdio + HTTP with bearer auth
  brief.py         news brief: candidates → editor LLM → top 7-10 stories with links
  bot/             Discord bot: monitor loop + brief + link replies
  web/             web UI: search, facets, item/author pages, curation, sources
  health.py        health checks
evals/             labelled data + harness + results
tests/             connector tests (recorded fixtures), pipeline, search
```
