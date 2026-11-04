-- Fixed topic taxonomy. Descriptions double as label definitions in the enrichment prompt.
insert into topics (slug, label, description) values
  ('manipulation',          'Manipulation',            'Grasping, dexterous hands, pick-and-place, bimanual and contact-rich manipulation.'),
  ('locomotion',            'Locomotion',              'Legged, wheeled or aerial movement; gait, balance, terrain traversal.'),
  ('humanoids',             'Humanoids',               'Humanoid robot platforms, whole-body control, humanoid companies and demos.'),
  ('vla-foundation-models', 'VLA / foundation models', 'Vision-language-action models, robot foundation models, generalist policies, world models.'),
  ('sim2real',              'Sim2real',                'Simulation, domain randomisation, synthetic data, transfer from sim to real hardware.'),
  ('slam-spatial-mapping',  'SLAM / spatial / mapping','SLAM, localisation, relocalisation, 3D reconstruction, scene graphs, shared maps, spatial computing.'),
  ('perception',            'Perception',              '2D/3D vision, depth, segmentation, tracking, tactile and multimodal sensing.'),
  ('hardware',              'Hardware',                'Actuators, sensors, robot bodies, compute, BOM and manufacturing.'),
  ('datasets-benchmarks',   'Datasets / benchmarks',   'New datasets, benchmarks, evaluation suites, leaderboards.'),
  ('multi-agent',           'Multi-agent',             'Fleets, multi-robot coordination, swarms, robots sharing information or maps.'),
  ('other',                 'Other',                   'Robotics-related but none of the above (policy, business, safety, tooling).')
on conflict (slug) do nothing;

-- Starter tracked sources. After this, Discord /follow and /track edit the table.
insert into sources (kind, value, added_by) values
  ('arxiv_category', 'cs.RO', 'seed'),
  ('arxiv_query',    'cat:cs.CV AND (abs:robot OR abs:SLAM OR abs:"visual localization" OR abs:"spatial")', 'seed'),
  ('arxiv_query',    'cat:cs.LG AND (abs:robot OR abs:"embodied" OR abs:"vision-language-action")', 'seed'),
  ('github_org',     'huggingface/lerobot', 'seed'),
  ('github_org',     'NVIDIA-Omniverse', 'seed'),
  ('github_org',     'google-deepmind', 'seed'),
  ('github_org',     'Physical-Intelligence', 'seed'),
  ('github_org',     'facebookresearch', 'seed'),
  ('github_query',   'topic:robotics stars:>50', 'seed'),
  ('hf_feed',        'daily_papers', 'seed'),
  ('hf_feed',        'models:robotics', 'seed'),
  ('hf_feed',        'datasets:lerobot', 'seed'),
  ('hn_query',       'robot', 'seed'),
  ('hn_query',       'humanoid', 'seed'),
  ('hn_query',       'robotics', 'seed'),
  ('alphaxiv',       'robotics', 'seed'),
  ('rss',            'https://spectrum.ieee.org/feeds/topic/robotics.rss', 'seed'),
  ('rss',            'https://www.therobotreport.com/feed/', 'seed'),
  ('x_account',      'physical_int', 'seed'),
  ('x_account',      'Figure_robot', 'seed'),
  ('x_account',      'UnitreeRobotics', 'seed'),
  ('x_account',      'DrJimFan', 'seed'),
  ('x_account',      'AukiNetwork', 'seed'),
  ('x_query',        'humanoid robot paper', 'seed'),
  ('x_query',        'vision-language-action model', 'seed'),
  ('hn_query',       'spatial computing', 'seed'),
  ('arxiv_query',    'all:"visual positioning" OR all:"visual relocalization"', 'seed')
on conflict (kind, value) do nothing;
