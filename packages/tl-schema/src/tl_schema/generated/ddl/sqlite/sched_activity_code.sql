CREATE TABLE IF NOT EXISTS sched_activity_code (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  activity_id TEXT NOT NULL,
  code_type TEXT NOT NULL,
  code_value TEXT NOT NULL,
  code_name TEXT NOT NULL,
  seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_activity_code_snapshot_activity ON sched_activity_code (snapshot_id, activity_id);
