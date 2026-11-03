CREATE TABLE IF NOT EXISTS cur_awp_path_step (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  path_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  position INTEGER NOT NULL,
  cwa_id TEXT NOT NULL,
  reason_code TEXT,
  actor TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_path_step_cwa ON cur_awp_path_step (cwa_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_path_step_path_version ON cur_awp_path_step (path_id, version, position);
