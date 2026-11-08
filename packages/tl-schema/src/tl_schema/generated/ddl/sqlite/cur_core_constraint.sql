CREATE TABLE IF NOT EXISTS cur_core_constraint (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  severity TEXT NOT NULL,
  category TEXT NOT NULL,
  source TEXT NOT NULL,
  owner TEXT,
  description_text TEXT,
  check_name TEXT,
  suppress_hash TEXT,
  clear_reason TEXT,
  target_kind TEXT,
  target_id TEXT,
  target_ref_type TEXT,
  target_ref_text TEXT,
  effective_at TEXT,
  due_at TEXT,
  cleared_at TEXT,
  cleared_by TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_core_constraint_scope_subject ON cur_core_constraint (scope, subject_id);
