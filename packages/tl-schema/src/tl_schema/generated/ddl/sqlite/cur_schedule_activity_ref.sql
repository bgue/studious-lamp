CREATE TABLE IF NOT EXISTS cur_schedule_activity_ref (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  schedule_id TEXT NOT NULL,
  schedule_code TEXT NOT NULL,
  activity_id TEXT NOT NULL,
  first_snapshot_id TEXT NOT NULL,
  first_snapshot_number INTEGER NOT NULL,
  present INTEGER NOT NULL DEFAULT 1,
  last_seen_snapshot_id TEXT,
  last_seen_number INTEGER,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_schedule_activity_ref_schedule_activity ON cur_schedule_activity_ref (schedule_id, activity_id);

CREATE INDEX IF NOT EXISTS ix_cur_schedule_activity_ref_scope_schedule ON cur_schedule_activity_ref (scope, schedule_id);
