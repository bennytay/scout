-- Hybrid search: full-text + vector + trigram (title/author/org), merged with reciprocal rank fusion.
-- Vector search here is exact over the filtered set on purpose: HNSW + WHERE filters silently loses
-- recall, and an exact cosine scan is milliseconds below ~100k rows. HNSW serves find_related.
create or replace function search_items(
  q               text,
  q_embedding     vector      default null,
  f_author        text        default null,
  f_org           text        default null,
  f_topic         text        default null,
  f_type          item_type   default null,
  f_source        text        default null,
  f_since         timestamptz default null,
  f_until         timestamptz default null,
  f_min_relevance real        default null,
  match_limit     int         default 10,
  rrf_k           int         default 60
) returns table (item_id bigint, score float8, matched text[])
language sql stable as $$
with filtered as materialized (
  select i.id, i.title, i.tsv, i.embedding, i.published_at
  from items i
  where (f_type is null or i.type = f_type)
    and (f_source is null or i.source = f_source
         or exists (select 1 from item_sources s where s.item_id = i.id and s.source = f_source))
    and (f_since is null or i.published_at >= f_since)
    and (f_until is null or i.published_at <  f_until)
    and (f_min_relevance is null or i.auki_relevance >= f_min_relevance)
    and (f_topic is null or exists (
          select 1 from item_topics t where t.item_id = i.id and t.topic_slug = f_topic))
    and (f_author is null or exists (
          select 1 from item_authors ia join authors a on a.id = ia.author_id
          where ia.item_id = i.id
            and (f_author <% a.name or f_author <% a.normalized_name
                 or lower(f_author) = any(a.aliases)
                 or lower(ltrim(f_author, '@')) in (lower(a.x_handle), lower(a.github_handle)))))
    and (f_org is null or exists (
          select 1 from item_orgs io join orgs o on o.id = io.org_id
          where io.item_id = i.id
            and (f_org <% o.name or f_org <% o.normalized_name or lower(f_org) = any(o.aliases) or lower(f_org) = lower(o.github_org))))
),
tq as (select websearch_to_tsquery('english', coalesce(q, '')) as query),
fts as (
  select f.id, row_number() over (order by ts_rank_cd(f.tsv, tq.query, 32) desc) as r
  from filtered f, tq
  where coalesce(q, '') <> '' and f.tsv @@ tq.query
  order by r limit 50
),
vec as (
  select f.id, row_number() over (order by f.embedding <=> q_embedding) as r
  from filtered f
  where q_embedding is not null and f.embedding is not null
  order by r limit 50
),
fuzzy as (
  select u.id, row_number() over (order by max(u.s) desc) as r
  from (
    select f.id, word_similarity(q, f.title) as s from filtered f where q <% f.title
    union all
    select ia.item_id, word_similarity(q, a.name)
      from authors a join item_authors ia on ia.author_id = a.id where q <% a.name
    union all
    select io.item_id, word_similarity(q, o.name)
      from orgs o join item_orgs io on io.org_id = o.id where q <% o.name
  ) u
  join filtered f on f.id = u.id
  where coalesce(q, '') <> ''
  group by u.id
  order by r limit 50
),
recent as (  -- filter-only queries ("everything by X", "humanoids this week")
  select f.id, row_number() over (order by f.published_at desc nulls last) as r
  from filtered f where coalesce(q, '') = ''
  order by r limit 50
),
hits as (
  select id, r, 'fts'    as src from fts
  union all select id, r, 'vec'    from vec
  union all select id, r, 'fuzzy'  from fuzzy
  union all select id, r, 'recent' from recent
)
select h.id,
       (sum(1.0 / (rrf_k + h.r)) * (1 + 0.2 * tanh(coalesce(max(fb.net), 0) / 2.0)))::float8,
       array_agg(h.src || ':' || h.r order by h.src)
from hits h
left join item_feedback fb on fb.item_id = h.id
group by h.id
order by 2 desc
limit match_limit;
$$;
