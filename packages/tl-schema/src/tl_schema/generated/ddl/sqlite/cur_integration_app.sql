CREATE TABLE IF NOT EXISTS cur_integration_app (
  app_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  name TEXT NOT NULL,
  label TEXT NOT NULL,
  description TEXT,
  owner TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_integration_app_integration_app_name ON cur_integration_app (name);

CREATE INDEX IF NOT EXISTS ix_cur_integration_app_scope ON cur_integration_app (scope);
