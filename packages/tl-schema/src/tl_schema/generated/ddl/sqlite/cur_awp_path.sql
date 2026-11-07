CREATE TABLE IF NOT EXISTS cur_awp_path (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  current_version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_path_scope ON cur_awp_path (scope);
