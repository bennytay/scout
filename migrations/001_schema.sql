-- Core schema. Applied by `scout migrate` (tracked in schema_migrations).
create extension if not exists vector;
create extension if not exists pg_trgm;

create type item_type as enum ('paper','repo','post','article','model','dataset','video');

create table items (
  id                    bigint generated always as identity primary key,
  canonical_url         text not null unique,
  type                  item_type not null,
  title                 text not null,
  summary               text,
  full_text             text,
  published_at          timestamptz,
  ingested_at           timestamptz not null default now(),
  source                text not null,              -- first-seen connector
  source_ref            text,                       -- native id in that source
  submitted_by          text,                       -- discord user, null if crawled
  arxiv_id              text,                       -- versionless; only when this item IS the paper
  doi                   text,
  metrics               jsonb not null default '{}',   -- keyed per source, merged on upsert
  entities              jsonb not null default '{}',   -- robots/datasets/benchmarks/methods
  auki_relevance        real check (auki_relevance between 0 and 1),
  auki_relevance_reason text,
  enrich_status         text not null default 'pending' check (enrich_status in ('pending','done','failed')),
  enrich_model          text,
  cost_usd              numeric(10,6) not null default 0,
  alerted_at            timestamptz,
  outlinks              text[] not null default '{}',  -- canonical URLs this item mentions
  embedding             vector(1536),
  tsv tsvector generated always as (
      setweight(to_tsvector('english', coalesce(title,'')),   'A') ||
      setweight(to_tsvector('english', coalesce(summary,'')), 'B') ||
      setweight(to_tsvector('english', left(coalesce(full_text,''), 100000)), 'C')
  ) stored
);
create unique index items_arxiv_key  on items (arxiv_id) where arxiv_id is not null;
create unique index items_doi_key    on items (lower(doi)) where doi is not null;
create index items_tsv_idx    on items using gin (tsv);
create index items_title_trgm on items using gin (title gin_trgm_ops);
create index items_emb_hnsw   on items using hnsw (embedding vector_cosine_ops);
create index items_pub_idx    on items (published_at desc);
create index items_outlinks_idx on items using gin (outlinks);

-- Every time a source sees an item. Powers "trending" (cross-source buzz).
create table item_sources (
  item_id    bigint not null references items on delete cascade,
  source     text not null,
  source_ref text not null default '',
  seen_at    timestamptz not null default now(),
  primary key (item_id, source, source_ref)
);

create table orgs (
  id              bigint generated always as identity primary key,
  name            text not null,
  normalized_name text not null unique,
  aliases         text[] not null default '{}',   -- lowercased
  kind            text check (kind in ('lab','company','university','other')),
  github_org      text unique,
  x_handle        text unique,
  website         text
);
create index orgs_name_trgm on orgs using gin (name gin_trgm_ops);

create table authors (
  id              bigint generated always as identity primary key,
  name            text not null,
  normalized_name text not null unique,
  aliases         text[] not null default '{}',
  arxiv_handle    text,
  x_handle        text unique,
  github_handle   text unique
);
create index authors_name_trgm on authors using gin (name gin_trgm_ops);

create table topics (
  slug        text primary key,
  label       text not null,
  description text not null
);

create table item_authors (
  item_id   bigint references items on delete cascade,
  author_id bigint references authors on delete cascade,
  position  smallint,
  primary key (item_id, author_id)
);
create index item_authors_author_idx on item_authors (author_id);

create table item_orgs (
  item_id bigint references items on delete cascade,
  org_id  bigint references orgs on delete cascade,
  primary key (item_id, org_id)
);
create index item_orgs_org_idx on item_orgs (org_id);

create table item_topics (
  item_id    bigint references items on delete cascade,
  topic_slug text references topics,
  confidence real not null default 1,
  primary key (item_id, topic_slug)
);
create index item_topics_topic_idx on item_topics (topic_slug);

create table item_links (
  src_item_id bigint references items on delete cascade,
  dst_item_id bigint references items on delete cascade,
  relation    text not null check (relation in ('implements','discusses','mentions','cites','same_work')),
  evidence    text,
  created_at  timestamptz not null default now(),
  primary key (src_item_id, dst_item_id, relation),
  check (src_item_id <> dst_item_id)
);
create index item_links_dst_idx on item_links (dst_item_id);

create table feedback (
  id         bigint generated always as identity primary key,
  item_id    bigint not null references items on delete cascade,
  user_id    text not null,
  signal     smallint not null check (signal in (-1, 1)),
  created_at timestamptz not null default now(),
  unique (item_id, user_id)
);
create view item_feedback as
  select item_id,
         sum(signal)::int                     as net,
         count(*) filter (where signal > 0)   as up,
         count(*) filter (where signal < 0)   as down
  from feedback group by item_id;

-- Tracked accounts/keywords/feeds. Editable via Discord /follow /track /unfollow.
create table sources (
  id                   bigint generated always as identity primary key,
  kind                 text not null check (kind in ('arxiv_category','arxiv_query','x_account','x_query',
                         'github_org','github_query','hf_feed','hn_query','rss','alphaxiv')),
  value                text not null,
  enabled              boolean not null default true,
  added_by             text,
  created_at           timestamptz not null default now(),
  last_run_at          timestamptz,
  last_success_at      timestamptz,
  last_error           text,
  consecutive_failures int not null default 0,
  unique (kind, value)
);

create table ingest_runs (
  id          bigint generated always as identity primary key,
  connector   text not null,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  status      text not null default 'running' check (status in ('running','ok','partial','failed')),
  fetched     int not null default 0,
  inserted    int not null default 0,
  duplicates  int not null default 0,
  failed      int not null default 0,
  cost_usd    numeric(10,6) not null default 0,
  error       text
);

-- Draft X posts. Never auto-published: a human approves in Discord.
create table post_drafts (
  id                 bigint generated always as identity primary key,
  week_of            date not null,
  body               text not null,
  item_ids           bigint[] not null,
  status             text not null default 'pending' check (status in ('pending','approved','rejected')),
  discord_message_id text,
  decided_by         text,
  created_at         timestamptz not null default now()
);
