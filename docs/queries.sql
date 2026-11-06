-- Looking inside Scout's database. Plain SQL: run in any Postgres client (TablePlus, Postico, DBeaver, psql).
--   Connection: postgresql://scout:scout@localhost:54329/scout_demo
--   Without a client: docker exec -it scout-db-1 psql -U scout -d scout_demo

-- 1. What's in there: one row per table, with counts.
select 'items' as table_name, count(*) from items
union all select 'authors', count(*) from authors
union all select 'orgs', count(*) from orgs
union all select 'item_links (post -> paper/code)', count(*) from item_links
union all select 'sources (X accounts + searches)', count(*) from sources where enabled
union all select 'briefs', count(*) from briefs
union all select 'ingest_runs (scans)', count(*) from ingest_runs;

-- 2. Items by type.
select type, count(*) from items group by 1 order by 2 desc;

-- 3. The newest items: what each row holds.
select id, type, title, canonical_url, published_at, importance, auki_relevance, summary
from items order by ingested_at desc limit 20;

-- 4. An X post and everything it led to (the paper, code, model it links to).
select p.title as post, l.relation, d.type, d.title as linked_item, d.canonical_url
from item_links l
join items p on p.id = l.src_item_id
join items d on d.id = l.dst_item_id
where p.type = 'post'
order by p.importance desc nulls last limit 20;

-- 5. Search by author (fuzzy: 'hutter', 'levine').
select a.name, a.x_handle, i.type, i.title, i.published_at
from authors a
join item_authors ia on ia.author_id = a.id
join items i on i.id = ia.item_id
where a.name ilike '%hutter%'
order by i.published_at desc nulls last;

-- 6. Search by topic.
select i.type, i.title, i.importance, i.published_at
from item_topics t join items i on i.id = t.item_id
where t.topic_slug = 'humanoids'
order by i.importance desc nulls last limit 20;

-- 7. Keyword + meaning search: the same hybrid function the bot and MCP use. In SQL you pass text only
--    (the meaning half needs a query embedding, which the app computes); filters are named arguments.
select i.type, i.title, round(s.score::numeric, 4) as score, s.matched
from search_items('humanoid factory deployment', match_limit => 10) s join items i on i.id = s.item_id
order by s.score desc;

-- 8. Topic coverage over the last 14 days.
select t.topic_slug, count(*) as items, round(avg(i.importance)::numeric, 2) as avg_importance
from item_topics t join items i on i.id = t.item_id
where i.ingested_at > now() - interval '14 days'
group by 1 order by 2 desc;

-- 9. The X radar: which trusted accounts actually produce kept posts.
select s.value as handle, s.config->>'tier' as tier, coalesce(x.kept, 0) as kept, coalesce(x.judged, 0) as judged
from sources s left join x_accounts x on x.handle = lower(s.value)
where s.kind = 'x_account' and s.enabled
order by kept desc, judged desc;

-- 10. Scan history: seen, filtered, kept, cost.
select started_at, fetched, dropped, inserted, cost_usd, status
from ingest_runs where connector = 'x' order by started_at desc limit 20;
