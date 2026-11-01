CREATE TABLE IF NOT EXISTS cur_awp_path (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  current_version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_path_scope ON cur_awp_path (scope);
