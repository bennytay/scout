# Decisions

Short records of the non-obvious choices, and why. Newest last.

### D1. Plain Postgres access (psycopg) instead of supabase-py
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
