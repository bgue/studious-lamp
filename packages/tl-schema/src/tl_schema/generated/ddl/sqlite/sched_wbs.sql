CREATE TABLE IF NOT EXISTS sched_wbs (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  wbs_id TEXT NOT NULL,
  parent_wbs_id TEXT,
  short_name TEXT NOT NULL,
  name TEXT NOT NULL,
  path TEXT NOT NULL,
  is_project_node INTEGER NOT NULL,
  seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_wbs_snapshot ON sched_wbs (snapshot_id, seq);
