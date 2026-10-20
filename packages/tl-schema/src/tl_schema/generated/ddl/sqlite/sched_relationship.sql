CREATE TABLE IF NOT EXISTS sched_relationship (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  pred_activity_id TEXT NOT NULL,
  succ_activity_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL,
  lag_hr REAL NOT NULL,
  seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_relationship_snapshot_pred ON sched_relationship (snapshot_id, pred_activity_id);

CREATE INDEX IF NOT EXISTS ix_sched_relationship_snapshot_succ ON sched_relationship (snapshot_id, succ_activity_id);
