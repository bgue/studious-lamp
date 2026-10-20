CREATE TABLE IF NOT EXISTS sched_activity (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  activity_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  name TEXT NOT NULL,
  wbs_id TEXT NOT NULL,
  wbs_path TEXT NOT NULL,
  task_type TEXT NOT NULL,
  status TEXT NOT NULL,
  calendar_id TEXT NOT NULL,
  original_duration_hr REAL,
  remaining_duration_hr REAL,
  early_start TEXT,
  early_finish TEXT,
  late_start TEXT,
  late_finish TEXT,
  actual_start TEXT,
  actual_finish TEXT,
  target_start TEXT,
  target_finish TEXT,
  total_float_hr REAL,
  free_float_hr REAL,
  percent_complete REAL NOT NULL,
  percent_type TEXT,
  constraint_type TEXT,
  constraint_date TEXT,
  critical INTEGER NOT NULL,
  longest_path INTEGER NOT NULL,
  seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_sched_activity_snapshot_activity ON sched_activity (snapshot_id, activity_id);

CREATE INDEX IF NOT EXISTS ix_sched_activity_scope_activity ON sched_activity (scope, activity_id);

CREATE INDEX IF NOT EXISTS ix_sched_activity_snapshot_float ON sched_activity (snapshot_id, total_float_hr);

CREATE INDEX IF NOT EXISTS ix_sched_activity_snapshot_start ON sched_activity (snapshot_id, early_start);
