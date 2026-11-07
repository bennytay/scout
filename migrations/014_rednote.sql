-- RedNote (小红书): keyword searches through a self-hosted xiaohongshu-mcp server. See docs/rednote.md.
-- Chinese robotics researchers and students post paper explainers, demo videos and lab news here first.
alter table sources drop constraint if exists sources_kind_check;
alter table sources add constraint sources_kind_check check (kind in ('arxiv_category','arxiv_query','x_account',
  'x_query','github_org','github_query','hf_feed','hn_query','rss','alphaxiv','rednote_query'));

-- Queries pair a robotics term with a research word so results lean to papers/code, not shopping.
insert into sources (kind, value, added_by, config) values
  ('rednote_query', '具身智能 论文', 'seed', '{"tier": "research"}'),
  ('rednote_query', '机器人 arxiv', 'seed', '{"tier": "research"}'),
  ('rednote_query', '人形机器人 开源', 'seed', '{"tier": "research"}'),
  ('rednote_query', 'VLA 机器人', 'seed', '{"tier": "research"}'),
  ('rednote_query', '灵巧手 论文', 'seed', '{"tier": "research"}'),
  ('rednote_query', '机器人 强化学习 论文', 'seed', '{"tier": "research"}'),
  ('rednote_query', '世界模型 机器人', 'seed', '{"tier": "research"}'),
  ('rednote_query', 'SLAM 论文', 'seed', '{"tier": "research"}'),
  ('rednote_query', '机器人 数据集', 'seed', '{"tier": "research"}'),
  ('rednote_query', '具身智能 融资', 'seed', '{"tier": "news"}')
on conflict (kind, value) do nothing;
