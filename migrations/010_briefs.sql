-- The news brief: an editor LLM clusters the window's items into 7-10 stories (X-first, with supporting links).
create table briefs (
  id            bigint generated always as identity primary key,
  created_at    timestamptz not null default now(),
  window_start  timestamptz not null,
  window_end    timestamptz not null,
  n_candidates  int not null,
  n_new_items   int not null,
  model         text not null,
  cost_usd      numeric(10,6) not null default 0,
  stories       jsonb not null,        -- [{headline, why, hot, links: [{label, url, item_id, type}]}]
  sources       jsonb not null default '{}'  -- per-source new-item counts in the window
);
create index briefs_created_idx on briefs (created_at desc);
