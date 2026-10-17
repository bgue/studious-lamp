CREATE TABLE IF NOT EXISTS cur_schedule_schedule_snapshot (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  schedule_id TEXT NOT NULL,
  schedule_code TEXT NOT NULL,
  number INTEGER NOT NULL,
  p6_project_option TEXT,
  source_file_id TEXT,
  source_name TEXT,
  source_sha256 TEXT,
  source_size INTEGER,
  requested_by TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  data_date TEXT,
  p6_version TEXT,
  p6_project TEXT,
  activity_count INTEGER,
  relationship_count INTEGER,
  wbs_count INTEGER,
  calendar_count INTEGER,
  code_count INTEGER,
  udf_count INTEGER,
  error_count INTEGER,
  warning_count INTEGER,
  report_file_id TEXT,
  raw_file_id TEXT,
  typed_sha256 TEXT,
  raw_sha256 TEXT,
  built_at TEXT,
  published_at TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_schedule_schedule_snapshot_schedule_number ON cur_schedule_schedule_snapshot (schedule_id, number);

CREATE INDEX IF NOT EXISTS ix_cur_schedule_schedule_snapshot_schedule_date ON cur_schedule_schedule_snapshot (schedule_id, data_date);

CREATE INDEX IF NOT EXISTS ix_cur_schedule_schedule_snapshot_scope_schedule ON cur_schedule_schedule_snapshot (scope, schedule_id);
