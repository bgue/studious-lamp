CREATE TABLE IF NOT EXISTS cur_schemareg_waiver (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  project TEXT COLLATE "C" NOT NULL,
  path TEXT COLLATE "C" NOT NULL,
  number BIGINT NOT NULL,
  reason TEXT COLLATE "C" NOT NULL,
  expires TEXT COLLATE "C" NOT NULL,
  requested_by TEXT COLLATE "C" NOT NULL,
  approver TEXT COLLATE "C",
  approved_at TEXT COLLATE "C",
  revoked_by TEXT COLLATE "C",
  revoked_at TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_schemareg_waiver_scope_path ON cur_schemareg_waiver (scope, path);
