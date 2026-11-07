CREATE TABLE IF NOT EXISTS cur_awp_constraint (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  iwp_id TEXT NOT NULL,
  constraint_type TEXT NOT NULL,
  source TEXT NOT NULL,
  owner TEXT NOT NULL,
  need_by TEXT,
  description_text TEXT,
  check_name TEXT,
  raised_at TEXT,
  cleared_at TEXT,
  cleared_by TEXT,
  clear_reason TEXT,
  suppress_hash TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_constraint_scope_iwp ON cur_awp_constraint (scope, iwp_id);
