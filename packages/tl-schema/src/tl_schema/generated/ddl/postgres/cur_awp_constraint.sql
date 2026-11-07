CREATE TABLE IF NOT EXISTS cur_awp_constraint (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  iwp_id TEXT COLLATE "C" NOT NULL,
  constraint_type TEXT COLLATE "C" NOT NULL,
  source TEXT COLLATE "C" NOT NULL,
  owner TEXT COLLATE "C" NOT NULL,
  need_by TEXT COLLATE "C",
  description_text TEXT COLLATE "C",
  check_name TEXT COLLATE "C",
  raised_at TEXT COLLATE "C",
  cleared_at TEXT COLLATE "C",
  cleared_by TEXT COLLATE "C",
  clear_reason TEXT COLLATE "C",
  suppress_hash TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_constraint_scope_iwp ON cur_awp_constraint (scope, iwp_id);
