CREATE TABLE IF NOT EXISTS sched_udf_value (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  activity_id TEXT NOT NULL,
  udf_name TEXT NOT NULL,
  udf_label TEXT,
  value_type TEXT NOT NULL,
  value TEXT NOT NULL,
  seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_udf_value_snapshot_activity ON sched_udf_value (snapshot_id, activity_id);
