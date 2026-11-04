# Demo video script (≈4 minutes)

Audience: Nils (founder) and Freddie (COO). The story is: **it watches everything, it tells you what
matters, and you can dig into any of it three ways.** Show, don't explain. Keep code on screen under 30
seconds in total.

## Before you hit record (10 minutes ahead)

- [ ] `make db` (Postgres up)
- [ ] Clear the Discord feed channel so the first thing on screen is the new cycle
- [ ] `make demo` → the bot scans every source on a fresh demo database and posts the brief (~5 min).
      Start recording when you see `📡 Scanning:` appear, or record the brief arriving.
- [ ] In a second terminal: `DATABASE_URL=postgresql://scout:scout@localhost:54329/scout_demo make web`
      (so the web UI shows the same data as the feed)
- [ ] Claude Desktop configured with the MCP snippet from the README (pointing at the same `DATABASE_URL`)
- [ ] Have 2 links ready to paste: one X post about a robotics paper, one GitHub repo
- [ ] Browser tabs: Discord, http://127.0.0.1:8000/brief, Claude Desktop

## Script

**0:00–0:20 · The problem** *(Discord on screen, feed channel empty)*
> "Robotics news is spread across arXiv, X, GitHub, Hugging Face and Hacker News, plus whatever the team drops
> in Discord. Nobody can read 500 papers a week. So I built Scout: it watches all of it and tells us what
> matters to Auki."

**0:20–1:10 · Monitoring, live** *(the status line updates: `📡 Scanning: arXiv ⏳ …` → `✓ 56`)*
> "Every few hours it scans each source. That's one line, updating live. Every item gets read by Claude:
> summarised, tagged against a fixed topic list, and scored for relevance to Auki against a rubric I wrote
> about the posemesh."

*(the brief arrives)*
> "Then the part that matters: an editor model turns hundreds of items into the 7 to 10 stories of the day.
> X is the newsroom. When people are talking about something on X, that post leads, and it's linked to
> the actual paper, code and model. 🔥 means core to Auki: relocalization, shared maps, multi-robot."

*(click one 🔥 story's paper link, then come back)*
> "Every label is a link. And the editor can only cite things that are actually in the database, so it
> can't make up a link."

**1:10–1:40 · The team's links** *(paste the X post in the links channel)*
> "Anyone on the team can drop a link here."

*(⏳ → ✅, the 4-bullet reply)*
> "Four bullets: what it is, why it matters to Auki, topics and who, related things we already have. And it
> followed the post through to the paper and repo and linked them."

**1:40–2:40 · Search and maintain, directly** *(web UI, Brief tab → Search tab)*
> "For digging in there's a plain web UI, no AI needed. Same data, same search."

- Type `robots sharing a map of a building`:
  > "This is search by meaning: none of these papers use those words."
- Click topic **slam-spatial-mapping**, then a top author, to show the author page:
  > "Search by author and topic, which is what the brief asked for. Typo-tolerant, so 'Hutter' or 'Huter'
  > both work."
- Open an item and fix a topic → **Save curation**:
  > "When the model's wrong, we fix it here, and later automatic runs never overwrite a human decision."
- **Sources & health** tab:
  > "Every tracked source, its health, and exactly what it has cost so far."

**2:40–3:30 · Ask anything** *(Claude Desktop)*
> "And because it's an MCP server, any LLM can use it."

Ask: *"What's new on visual relocalization in the last week, who's behind it, and is there code?"*
> "It searched the database and answered with sources. This works in Claude, Cursor, or whatever the team uses."

Optional follow-up: *"Give me Marco Hutter's profile."*

**3:30–4:10 · Why trust it** *(README: eval table, then the architecture diagram)*
> "I measured it. On a hand-labelled set, Claude gets the main topic right about 90% of the time, and
> search put a right answer first for every test query. Running all of it costs about 17 dollars a month in Claude plus X
> credits. It all runs locally on one laptop."

**4:10–4:30 · Where it goes** *(README roadmap)*
> "The same pipeline can ingest our own notes and threads. Then it isn't just a news radar, it's the team's
> shared memory: an exocortex. Thanks!"

## If something goes wrong on camera

- **A source shows ⚠️:** say "and here's the health check doing its job." It's real.
- **The brief is slow:** cut to the web UI's Brief tab, which shows the last brief.
- **A link reply takes more than 10s** (a big README, or the paper following): keep talking about what it's
  doing, or cut.
