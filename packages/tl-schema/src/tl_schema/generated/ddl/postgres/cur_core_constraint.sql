CREATE TABLE IF NOT EXISTS cur_core_constraint (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  subject_id TEXT COLLATE "C" NOT NULL,
  phase TEXT COLLATE "C" NOT NULL,
  severity TEXT COLLATE "C" NOT NULL,
  category TEXT COLLATE "C" NOT NULL,
  source TEXT COLLATE "C" NOT NULL,
  owner TEXT COLLATE "C",
  description_text TEXT COLLATE "C",
  check_name TEXT COLLATE "C",
  suppress_hash TEXT COLLATE "C",
  clear_reason TEXT COLLATE "C",
  target_kind TEXT COLLATE "C",
  target_id TEXT COLLATE "C",
  target_ref_type TEXT COLLATE "C",
  target_ref_text TEXT COLLATE "C",
  effective_at TEXT COLLATE "C",
  due_at TEXT COLLATE "C",
  cleared_at TEXT COLLATE "C",
  cleared_by TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_core_constraint_scope_subject ON cur_core_constraint (scope, subject_id);
