CREATE TABLE IF NOT EXISTS cur_awp_cwa (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  location_text TEXT,
  retired INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_awp_cwa_scope_code ON cur_awp_cwa (scope, code);

CREATE INDEX IF NOT EXISTS ix_cur_awp_cwa_scope_code ON cur_awp_cwa (scope, code);
