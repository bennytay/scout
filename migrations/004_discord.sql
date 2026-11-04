-- Maps bot messages (thread replies, alerts) to items, so 👍/👎 reactions land on the right item.
create table discord_messages (
  message_id text primary key,
  item_id    bigint references items on delete cascade,
  draft_id   bigint references post_drafts on delete cascade,
  kind       text not null check (kind in ('ingest_reply','alert','digest','draft')),
  created_at timestamptz not null default now()
);
create index discord_messages_item_idx on discord_messages (item_id);
