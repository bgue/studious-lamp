CREATE TABLE IF NOT EXISTS cur_schemareg_waiver (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  project TEXT NOT NULL,
  path TEXT NOT NULL,
  number INTEGER NOT NULL,
  reason TEXT NOT NULL,
  expires TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  approver TEXT,
  approved_at TEXT,
  revoked_by TEXT,
  revoked_at TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_schemareg_waiver_scope_path ON cur_schemareg_waiver (scope, path);
