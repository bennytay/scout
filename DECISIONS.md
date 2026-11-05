# Decisions

Short records of the non-obvious choices, and why. Newest last.

### D1. Plain Postgres access (psycopg), no Supabase client
Supabase is "just Postgres". Talking SQL directly means the same code runs against local docker (tests, CI,
evals) and Supabase, and the hybrid search can live in one SQL function. Migrations are plain `.sql` files
applied in order by `scout migrate` (tracked in `schema_migrations`). No ORM.

### D2. Hybrid search = one SQL function, RRF over four rankers
`search_items()` fuses full-text (`ts_rank_cd` on a weighted tsvector), vector cosine similarity, and pg_trgm
`word_similarity` on title, author and org names, with reciprocal rank fusion (k=60). A fourth "recent" ranker
handles filter-only queries ("everything by Levine"). Each hit returns `matched` (e.g. `['fts:1','vec:3']`), so
ranking is explainable and debuggable.

### D3. Exact vector search inside filtered search; HNSW only for unfiltered neighbours
HNSW with WHERE filters silently drops recall (the index returns the top-k *before* filtering). Below ~100k
rows an exact cosine scan over the filtered set takes milliseconds and is always correct. The HNSW index serves
`find_related` (unfiltered). Revisit beyond ~200k items (pgvector iterative scans, or partitioning by type).

### D4. Semantic dedupe only for posts/articles
The brief says dedupe on embedding similarity > 0.92. Applied blindly, that would merge v1.2 and v1.3 of a
release, or two papers from the same group. Papers, repos, models and datasets have strong identifiers
(canonical URL, arXiv ID, DOI), so they are deduped on those only. Similarity dedupe catches the case it is good
at: the same news story syndicated across sites.

### D5. Cross-source sightings instead of overwriting
When a known item is seen again (HF Daily Papers, an HN post linking an arXiv paper, a Discord share), we add
an `item_sources` row and merge metrics per source (`{"hf_upvotes":…, "hn_points":…}`). "Seen in 3 sources" is
the best cheap trending signal there is, and nothing is lost.

### D6. Links resolve in either arrival order
Items store `outlinks` (canonical URLs + inline arXiv IDs from READMEs and posts). On insert we link forward
(things I mention that we already have) *and* backward (things that already mention me). So a repo ingested
before its paper still gets linked once the paper arrives. Relations: `implements` (repo/model/dataset → paper),
`discusses` (post/article → paper/repo), `mentions` (anything else).

### D7. Enrichment: Claude Haiku 5.5 by default, structured output, one call per item
Cheap ($0.10/$0.50 per MTok), and structured output (`messages.parse` with a Pydantic schema) guarantees valid
JSON, so there's no retry-on-bad-JSON loop. The provider is one adapter (`providers/llm.py`): `LLM_PROVIDER=openai`
switches it, and `fake` is a deterministic keyword heuristic so the whole system runs, tests and evals with zero
keys. Source metadata beats the LLM for authors when available (arXiv/HF author lists are authoritative). If
enrichment fails, the item is still stored with `enrich_status='failed'`, and `scout enrich-retry` re-runs it.

### D8. The Auki relevance rubric is a prompt file, not code
`prompts/auki_context.md` describes what Auki cares about, with score bands. The team can tune "what matters"
without a deploy. 👍/👎 then nudges ranking on top (search: ×(1 + 0.2·tanh(net/2)); trending: +2·tanh(net/2)).
Feedback boosts ranking and never rewrites the LLM's score, so you can always tell the two apart.

### D9. X without the paid X API
The paid X API is out of scope, and automating the Grok UI in the X app breaks X's terms and is brittle. Two
paths instead:
1. **Monitoring** (tracked accounts and queries) goes through xAI's API: Grok with its `x_search` tool, asked
   to return posts as JSON. Needs `XAI_API_KEY`; costs cents per call; runs 3×/day. *The request shape follows
   xAI's Responses API; until it's verified against a live key, the test uses a synthetic fixture
   (`tests/fixtures/xai_response_synthetic.json`, clearly labelled).*
2. **Shared links**: any x.com link posted in Discord is resolved via the public fxtwitter embed API (text,
   author, likes). No key. This path is verified against a recorded real response.

### D10. alphaXiv is optional and fails soft
Its feed API is unofficial (`api.alphaxiv.org/papers/v3/feed`). The connector filters to robotics and
arXiv-backed entries, and returns `[]` on any error. alphaXiv is used as an attention signal (votes, 7-day
visits), not as a primary source.

### D11. GitHub Actions for ingestion, one small always-on box for bot + MCP
Connectors are batch jobs, so they run on Actions cron (free for public repos), as a matrix with
`fail-fast: false` (per-connector isolation). After every run a health job posts problems to Discord via
webhook. The bot and the MCP HTTP server need to stay up, so they share one container (Dockerfile; Railway or Fly).

### D12. Discord: `/track` fans a keyword out to per-source queries
`/track "visual positioning"` creates four tracked sources (arXiv full-text query within cs.RO/CV/LG/AI, HN,
GitHub search, X query). One concept, one table, and `/unfollow` disables them together.

### D13. Draft posts are never published
Weekly drafts are written in Auki's voice (`prompts/auki_voice.md`), stored in `post_drafts`, and posted to
Discord with ✅/❌. Approval only records the decision. Publishing stays a human action by design.

### D14. Evals: honest labels, a baseline in CI
56 recent real papers, labelled with topics and an Auki-relevance band, plus 21 search queries and 5 author
queries with relevant sets. Labels were drafted by the AI pair-programmer and need a human review pass before
the numbers are quoted as "hand-labelled". CI runs the eval with the offline heuristic providers as a regression
guard for search. The README reports both the heuristic baseline and the real-provider run.

### D15. MCP SDK 2.x (`MCPServer`)
The official Python SDK renamed FastMCP to `MCPServer` in 2.x. HTTP uses the SDK's streamable-HTTP app wrapped
in a bearer-token middleware (simplest auth that works with any client). DNS-rebinding protection is turned
off because it targets browser→localhost attacks, and this is a token-protected remote service.

### D16. Run locally, Claude only (supersedes parts of D1, D7, D9, D11)
For the demo the whole system runs on one laptop: Postgres in docker, the scheduler instead of the Actions
cron, and the bot and MCP on stdio. Supabase is unnecessary. The code still targets any Postgres, so hosting is
a `DATABASE_URL` change. Claude is the only paid model provider.

### D17. Local embeddings (fastembed, bge-small-en-v1.5, 384-d)
Claude has no embeddings endpoint, and "Claude only" rules out OpenAI. bge-small via ONNX on CPU is free, needs
no key, embeds ~40 docs/s, and scored **P@5 0.85** on the eval set (vs 0.72 for the hash baseline). Queries use
bge's retrieval instruction prefix (`query_embed`). The provider stays swappable: `EMBEDDING_PROVIDER=openai`
requests 384 dimensions so the schema doesn't change. Migration 005 resized the column and `scout reembed`
rebuilds vectors after a switch.

### D18. Official X API v2 replaces xAI/Grok (supersedes D9's monitoring path)
With pay-per-use credits, the official API is the most direct source. Cost controls are built in: a stored
`since_id` per source (only new posts are read), a cached user id (no repeat lookups), `X_MAX_RESULTS` per
source, search restricted to `has:links -is:retweet -is:reply lang:en`, and X runs 3×/day versus 6×/day for
the free sources. Shared links still go to the free fxtwitter endpoint first, and the API is the fallback.

### D19. Strip the bot back to the brief: a passive feed + team links (supersedes D12, D13; drops feedback from D8)
The bot had grown slash commands (/ask, /follow, /track, /unfollow, /sources, /digest), reactions-as-feedback,
a weekly digest and draft posts. That's a lot of surface for a brief that asks to *follow sources, take the
team's links, and be searchable*. Now:
- **Monitoring is visible**: the bot runs the connectors itself and posts one bulleted message per source run,
  with every item a link, 🔥 + reason for Auki-relevant items, and LLM-judged off-topic items (< 0.3) counted
  but hidden. "Nothing new" is posted too, so you can see the monitor is alive.
- **Team links** get 4 bullets (what / why Auki / topics + who / related) instead of a thread and an embed.
- **Questions go through MCP**, where the user's own LLM is the interface. There's no second chat UI to maintain.
Migration 007 drops `feedback`, `post_drafts` and `discord_messages`; search ranking is pure RRF again.
Found while testing the feed: Hacker News' Algolia search matched "SLAM" to "slams" and loosely matched
unrelated stories, so typo tolerance is off and matching is restricted to title/url.

### D20. The news brief: a reasoning layer, X-first (supersedes the per-source feed in D19)
Per-source updates ("56 arXiv papers, 52 HF items…") were fragmented: the reader had to do the synthesis.
Now each cycle ends with one brief of the top 7–10 *stories*. Design choices:
- **Clustering is the LLM's job, not ours.** Candidates come with explicit links (post→paper, repo→paper) and
  nearest neighbours by meaning, and the editor decides what's one story. Hand-written clustering rules
  (shared URLs only) would miss "a post about the paper with no link".
- **X is the newsroom.** When a post covers a story it's the primary link, and the paper, code and model are
  supporting links. Without an X key the brief still works from the other sources plus team-shared X links.
- **No invented links.** The editor returns candidate ids only; URLs are filled in from the database, and
  unknown or reused ids are dropped.
- **Model split:** Opus 5.5 for the brief (one editorial reasoning call per cycle, ~$0.065); Haiku 5.5 for
  per-item enrichment (hundreds of calls). `BRIEF_MODEL` is configurable.
- **Visible monitoring without spam:** one status line, edited in place as each source finishes.

### D21. A web UI for direct search and maintenance (refines "no web frontend")
The brief said no web frontend; the interface was MCP and Discord. But "maintain a database, searchable by
author and topic" needs a direct, non-LLM way to browse, fix and curate: an LLM is the wrong tool for
"show me everything tagged humanoids by NVIDIA last week, then fix this one's topic". Options weighed:
generic Postgres GUIs (no hybrid search, raw tables), Metabase (heavy, dashboards not search), Datasette
(SQLite only), a TUI (bad on video), Notion/Airtable sync (two sources of truth). Chosen: a small
server-rendered Starlette app on the **same search function as MCP**, so answers never disagree. It has no
JS build and no new dependencies. Human edits are marked `curated_at`, and re-enrichment never overwrites them.

### D22. Context search: entities indexed; explicit syntax binds every ranker
Entities extracted by the LLM are part of the full-text index. Quoted phrases and `-exclusions` now filter
the vector and fuzzy rankers too (before, `-aerial` still returned an aerial paper via the vector ranker).
Tried and rejected: letting long questions match on *any* word. Even ranked after all-word matches, it cost
P@5 0.85 → 0.80 on the eval set, because weak lexical hits compound with vector hits in RRF. Paraphrased
questions are the vector ranker's job.

### D23. X-first: X is the only scheduled source; arXiv / GitHub / HF become resolvers (supersedes D19–D21's source list)
Robotics news breaks on X. A lab posts the paper, the demo video and the repo; arXiv and GitHub are where the
details live, not where the news is. So Scout scans only X on a schedule, and fetches the arXiv paper, GitHub
repo or HF model **because a kept post links to it** (at most 3 per post, linked post → paper). Hacker News,
RSS and alphaXiv were deleted rather than kept "just in case": every extra source is more noise for the brief
and more code to maintain. Their old `sources` rows stay in the table, disabled, for history.

### D24. The X signal funnel: cheap before expensive, precision over recall
X is mostly noise, so the order is: query design → free rules → a Haiku label → an Opus editor.
- **Radar** accounts are packed into `from:` OR-queries under the 512-character limit (verified against
  the API). 64 accounts take 3 requests. Per-source `until` cursors mean every post is read, and paid for, once.
  Radar accounts are trusted: they skip the rules and go to the judge.
- **Discovery** only searches for posts that link to research. A research link is the cheapest strong
  anti-spam signal. It reads a window ending 6h ago, so engagement exists before the gate judges it.
- **Gate** (pure, unit-tested): spam lexicon, research link, ≥10 likes, and below 50 likes also ≥200 followers
  and ≥90-day account age. Plus a per-author cap and copy-paste dedupe. Thresholds were set from one real
  scan and live in config.
- **Judge**: a `signal` field added to the existing enrichment call (news | discussion | promo | off_topic |
  noise), so there's no second LLM call. Posts the team shares in Discord are never judged out.
- **Learn**: per-account kept/judged counts. A non-radar account with ≥3 kept posts and a ≥50% kept rate is
  suggested once. A human runs `/follow`; the radar never edits itself.
- **Measured** on 62 real posts labelled by content alone: precision 1.00. Recall is 1.00 for radar and 0.16
  for discovery, because the misses are mostly arXiv-mirror bots with no engagement. That trade-off is
  intended: the brief wants what people are discussing. It's published, not hidden.
- Scan every 2h, brief every 6h, so the feed isn't spammed.

### D25. No dashboard: one search, filled in by Claude or by a slash command (supersedes D21)
The web UI was removed. "Search by author and topic" doesn't need a second interface. It's the same `search()`
with structured fields. For questions, Claude fills them (`ask`: plan → search → cited answer, topped up with
a plain search when the filters were too strict). For lookups, Discord slash commands fill them with no LLM:
`/author` (autocomplete from the authors table, word-start matches first), `/topic`, and `/recent`, which
answers "what's stored?". MCP was trimmed to 4 tools for the same reason: `author_profile`, `trending` and
`digest` were just search with extra steps. The OpenAI adapters went too (Claude only).

### D26. General robotics scope: `importance` ranks, Auki relevance only marks (refines D20, D24)
Scout was quietly an Auki-relevance filter: the brief dropped any candidate below 0.3 Auki relevance and ranked
by it, and discovery only accepted posts linking to research. So a big humanoid IPO or a drone-delivery funding
round could fall out. Now:
- **Two scores, one call.** Enrichment adds `importance` (0–1, general significance for robotics, rubric in
  `prompts/enrich.md`) next to `auki_relevance`. Importance selects and ranks brief candidates, orders
  `/recent` and lists, and is shown on every item. Auki relevance is a 🔥 marker and a tie-breaker.
- **Wider sources.** The radar adds autonomous driving, drones, industrial, surgical and more humanoid makers.
  Discovery adds a drones, driving and surgical research search, plus a general-news search (launches,
  funding, deployments). That news doesn't link to research, so the gate holds it to ≥50 likes and ≥1,000
  followers instead. When a post matches several searches, the first one wins (radar, then research, then
  news), so the stricter bar only applies to posts found only by the news search.
- **Measured:** the X signal eval is unchanged (precision 1.00). On the demo data, the brief went from 41 to
  114 candidates, the Agility IPO moved from #7 to #1, and a drone-inspection story entered the top 10.
- Existing items were backfilled with `importance` by re-enrichment ($0.05 for 362 items).
