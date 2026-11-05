-- Broaden from "what matters to Auki" to robotics news in general.
-- `importance` (0-1, general significance for robotics) now drives what is surfaced and how it's ranked;
-- `auki_relevance` stays as a secondary marker (🔥 in the brief).
alter table items add column if not exists importance real;
create index if not exists items_importance_idx on items (importance desc nulls last);

-- Discovery, general news: launches, funding, deployments. These posts link to company sites and press, not
-- arXiv, so the gate holds them to a higher engagement bar instead of requiring a research link.
insert into sources (kind, value, added_by, config) values
  ('x_query', '(robot OR robots OR robotics OR humanoid OR robotaxi OR drone OR "autonomous vehicle" OR exoskeleton) (launches OR launched OR unveils OR announces OR raises OR funding OR acquires OR acquisition OR deploys OR deployment OR introducing) has:links', 'seed', '{"tier": "news"}'),
  ('x_query', '(url:arxiv.org OR url:github.io OR url:openreview.net) (drone OR UAV OR "autonomous driving" OR "self-driving" OR "surgical robot" OR exoskeleton OR "soft robot" OR "robot hand")', 'seed', '{"tier": "discovery"}')
on conflict (kind, value) do update set enabled = true, config = excluded.config;

-- Radar: add accounts beyond Auki's niche: industrial, warehouse, drones, autonomous driving, surgical, more humanoids.
insert into sources (kind, value, added_by, config)
select 'x_account', h, 'seed', jsonb_build_object('tier', t) from (values
  -- autonomous driving, drones, industrial/warehouse, surgical, more humanoid makers
  ('Waymo','company'), ('zipline','company'), ('SkydioHQ','company'), ('Tesla_AI','company'), ('ABBRobotics','company'),
  ('anybotics','company'), ('UBTECHRobotics','company'), ('IntuitiveSurg','company'), ('clonerobotics','company'),
  ('fourierrobots','company'), ('AgibotTech','company'), ('dynarobotics','company'), ('Mentee_Robotics','company'),
  ('KyleVogt','company'), ('peteflorence','researcher'), ('BotJunkie','curator')
) as v(h, t)
on conflict (kind, value) do update set enabled = true, config = excluded.config;
