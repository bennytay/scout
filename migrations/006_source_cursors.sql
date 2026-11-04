-- Per-source incremental state (e.g. X user id + since_id) so paid APIs only return new posts.
alter table sources add column cursor jsonb not null default '{}';
