CREATE TABLE IF NOT EXISTS cur_schedule_schedule (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  schedule_type TEXT COLLATE "C" NOT NULL,
  owner TEXT COLLATE "C",
  p6_project TEXT COLLATE "C",
  current_snapshot_id TEXT COLLATE "C",
  current_snapshot_number BIGINT,
  current_data_date TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_schedule_schedule_scope_code ON cur_schedule_schedule (scope, code);
