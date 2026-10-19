CREATE TABLE IF NOT EXISTS sched_wbs (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  snapshot_id TEXT COLLATE "C" NOT NULL,
  wbs_id TEXT COLLATE "C" NOT NULL,
  parent_wbs_id TEXT COLLATE "C",
  short_name TEXT COLLATE "C" NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  path TEXT COLLATE "C" NOT NULL,
  is_project_node BOOLEAN NOT NULL,
  seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_wbs_snapshot ON sched_wbs (snapshot_id, seq);
