CREATE TABLE IF NOT EXISTS cur_awp_path_step (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  path_id TEXT COLLATE "C" NOT NULL,
  version BIGINT NOT NULL,
  position BIGINT NOT NULL,
  cwa_id TEXT COLLATE "C" NOT NULL,
  reason_code TEXT COLLATE "C",
  actor TEXT COLLATE "C" NOT NULL,
  recorded_at TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_path_step_cwa ON cur_awp_path_step (cwa_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_path_step_path_version ON cur_awp_path_step (path_id, version, position);
