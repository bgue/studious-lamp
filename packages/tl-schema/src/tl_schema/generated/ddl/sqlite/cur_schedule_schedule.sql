CREATE TABLE IF NOT EXISTS cur_schedule_schedule (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  schedule_type TEXT NOT NULL,
  owner TEXT,
  p6_project TEXT,
  current_snapshot_id TEXT,
  current_snapshot_number INTEGER,
  current_data_date TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_schedule_schedule_scope_code ON cur_schedule_schedule (scope, code);
