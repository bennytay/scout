-- X-first: X is the newsroom; arXiv / GitHub / Hugging Face are fetched only when a post links to them.

alter table sources add column if not exists config jsonb not null default '{}';  -- e.g. {"tier": "lab"}
alter table ingest_runs add column if not exists dropped int not null default 0;  -- X: gate + judge removals

-- Learn step: how often each account's posts survive the judge. Good non-radar accounts get suggested.
create table if not exists x_accounts (
  handle        text primary key,           -- lower-case, no @
  judged        int not null default 0,     -- posts that passed the free gate and reached the judge
  kept          int not null default 0,     -- ...and were kept (news / discussion)
  last_kept_at  timestamptz,
  suggested_at  timestamptz                 -- when the bot suggested adding it to the radar
);

-- Scheduled scanning is X only. Old sources stay in the table (history), disabled.
update sources set enabled = false where kind not in ('x_account', 'x_query');
update sources set enabled = false where kind = 'x_query';  -- the old keyword queries: too noisy

-- Discovery: posts from anyone that link to research. The connector appends -is:retweet -is:reply lang:en.
insert into sources (kind, value, added_by, config) values
  ('x_query', '(url:arxiv.org OR url:github.io OR url:openreview.net) (robot OR robotics OR humanoid OR quadruped OR "robot learning" OR "embodied AI")', 'seed', '{"tier": "discovery"}'),
  ('x_query', '(url:github.com OR url:huggingface.co) (robot OR robotics OR humanoid OR teleoperation OR "robot arm" OR VLA OR "vision-language-action")', 'seed', '{"tier": "discovery"}'),
  ('x_query', '(url:arxiv.org OR url:github.io OR url:github.com) (SLAM OR relocalization OR "visual localization" OR "3D reconstruction" OR "spatial computing" OR "scene graph" OR "gaussian splatting")', 'seed', '{"tier": "discovery"}')
on conflict (kind, value) do update set enabled = true, config = excluded.config;

-- Radar: accounts we trust. They skip the reputation rules and go straight to the judge.
-- Edit with /follow and /unfollow in Discord.
insert into sources (kind, value, added_by, config)
select 'x_account', h, 'seed', jsonb_build_object('tier', t) from (values
  -- robot companies
  ('physical_int','company'), ('Figure_robot','company'), ('UnitreeRobotics','company'), ('1x_tech','company'),
  ('agilityrobotics','company'), ('BostonDynamics','company'), ('Tesla_Optimus','company'), ('SkildAI','company'),
  ('ApptronikRobots','company'), ('sanctuaryai','company'), ('kscalelabs','company'), ('PollenRobotics','company'),
  ('covariant_ai','company'), ('wayve_ai','company'), ('theworldlabs','company'), ('AukiNetwork','company'),
  ('adcock_brett','company'), ('BerntBornich','company'),
  -- labs
  ('GoogleDeepMind','lab'), ('NVIDIARobotics','lab'), ('LeRobotHF','lab'), ('ToyotaResearch','lab'),
  ('leggedrobotics','lab'), ('MIT_CSAIL','lab'), ('StanfordAILab','lab'), ('berkeley_ai','lab'), ('CMU_Robotics','lab'),
  -- researchers
  ('DrJimFan','researcher'), ('svlevine','researcher'), ('chelseabfinn','researcher'), ('pabbeel','researcher'),
  ('RussTedrake','researcher'), ('yukez','researcher'), ('xiaolonw','researcher'), ('pathak2206','researcher'),
  ('LerrelPinto','researcher'), ('SongShuran','researcher'), ('kevin_zakka','researcher'), ('ericjang11','researcher'),
  ('hausman_k','researcher'), ('xiao_ted','researcher'), ('chris_j_paxton','researcher'), ('RemiCadene','researcher'),
  ('drfeifei','researcher'), ('jiajunwu_cs','researcher'), ('danfei_xu','researcher'), ('tonyzzhao','researcher'),
  ('chichengcc','researcher'), ('zipengfu','researcher'), ('YunzhuLiYZ','researcher'), ('andyzeng_','researcher'),
  ('davsca1','researcher'), ('AjdDavison','researcher'), ('Majumdar_Ani','researcher'), ('DorsaSadigh','researcher'),
  ('GuanyaShi','researcher'), ('ir0armeni','researcher'),
  -- curators who post robotics news early
  ('_akhaliq','curator'), ('TheHumanoidHub','curator'), ('IlirAliu_','curator'), ('CyberRobooo','curator'),
  ('TheRobotReport','curator'), ('IEEESpectrum','curator'), ('lukas_m_ziegler','curator')
) as v(h, t)
on conflict (kind, value) do update set enabled = true, config = excluded.config;
