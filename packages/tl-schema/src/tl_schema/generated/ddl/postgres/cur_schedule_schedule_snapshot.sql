CREATE TABLE IF NOT EXISTS cur_schedule_schedule_snapshot (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  schedule_id TEXT COLLATE "C" NOT NULL,
  schedule_code TEXT COLLATE "C" NOT NULL,
  number BIGINT NOT NULL,
  p6_project_option TEXT COLLATE "C",
  source_file_id TEXT COLLATE "C",
  source_name TEXT COLLATE "C",
  source_sha256 TEXT COLLATE "C",
  source_size BIGINT,
  requested_by TEXT COLLATE "C",
  attempts BIGINT NOT NULL DEFAULT 0,
  last_error TEXT COLLATE "C",
  data_date TEXT COLLATE "C",
  p6_version TEXT COLLATE "C",
  p6_project TEXT COLLATE "C",
  activity_count BIGINT,
  relationship_count BIGINT,
  wbs_count BIGINT,
  calendar_count BIGINT,
  code_count BIGINT,
  udf_count BIGINT,
  error_count BIGINT,
  warning_count BIGINT,
  report_file_id TEXT COLLATE "C",
  raw_file_id TEXT COLLATE "C",
  typed_sha256 TEXT COLLATE "C",
  raw_sha256 TEXT COLLATE "C",
  built_at TEXT COLLATE "C",
  published_at TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_schedule_schedule_snapshot_schedule_number ON cur_schedule_schedule_snapshot (schedule_id, number);

CREATE INDEX IF NOT EXISTS ix_cur_schedule_schedule_snapshot_schedule_date ON cur_schedule_schedule_snapshot (schedule_id, data_date);

CREATE INDEX IF NOT EXISTS ix_cur_schedule_schedule_snapshot_scope_schedule ON cur_schedule_schedule_snapshot (scope, schedule_id);
