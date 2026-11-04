-- Human curation from the web UI: when someone fixes an item's topics or relevance, record it, so later
-- re-enrichment never silently overwrites a human decision.
alter table items add column curated_at timestamptz;
alter table items add column curated_note text;
