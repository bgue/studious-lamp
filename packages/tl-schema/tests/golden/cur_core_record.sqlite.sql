CREATE TABLE IF NOT EXISTS cur_core_record (
  id TEXT PRIMARY KEY,
  key TEXT,
  type TEXT NOT NULL,
  scope TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT,
  psets_json TEXT NOT NULL DEFAULT '{}',
  voided INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL,
  effective_schema_hash TEXT,
  conformance TEXT NOT NULL DEFAULT 'ok',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_core_record_scope_key ON cur_core_record (scope, key);
