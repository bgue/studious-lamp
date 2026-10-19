CREATE TABLE IF NOT EXISTS sched_activity (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  snapshot_id TEXT COLLATE "C" NOT NULL,
  activity_id TEXT COLLATE "C" NOT NULL,
  task_id TEXT COLLATE "C" NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  wbs_id TEXT COLLATE "C" NOT NULL,
  wbs_path TEXT COLLATE "C" NOT NULL,
  task_type TEXT COLLATE "C" NOT NULL,
  status TEXT COLLATE "C" NOT NULL,
  calendar_id TEXT COLLATE "C" NOT NULL,
  original_duration_hr DOUBLE PRECISION,
  remaining_duration_hr DOUBLE PRECISION,
  early_start TEXT COLLATE "C",
  early_finish TEXT COLLATE "C",
  late_start TEXT COLLATE "C",
  late_finish TEXT COLLATE "C",
  actual_start TEXT COLLATE "C",
  actual_finish TEXT COLLATE "C",
  target_start TEXT COLLATE "C",
  target_finish TEXT COLLATE "C",
  total_float_hr DOUBLE PRECISION,
  free_float_hr DOUBLE PRECISION,
  percent_complete DOUBLE PRECISION NOT NULL,
  percent_type TEXT COLLATE "C",
  constraint_type TEXT COLLATE "C",
  constraint_date TEXT COLLATE "C",
  critical BOOLEAN NOT NULL,
  longest_path BOOLEAN NOT NULL,
  seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_sched_activity_snapshot_activity ON sched_activity (snapshot_id, activity_id);

CREATE INDEX IF NOT EXISTS ix_sched_activity_scope_activity ON sched_activity (scope, activity_id);

CREATE INDEX IF NOT EXISTS ix_sched_activity_snapshot_float ON sched_activity (snapshot_id, total_float_hr);

CREATE INDEX IF NOT EXISTS ix_sched_activity_snapshot_start ON sched_activity (snapshot_id, early_start);
