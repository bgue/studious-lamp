CREATE TABLE IF NOT EXISTS cur_core_record (
  id TEXT PRIMARY KEY,
  key TEXT,
  type TEXT NOT NULL,
  scope TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT,
  psets_json JSONB NOT NULL DEFAULT '{}',
  voided BOOLEAN NOT NULL DEFAULT FALSE,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL,
  effective_schema_hash TEXT,
  conformance TEXT NOT NULL DEFAULT 'ok',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_core_record_scope_key ON cur_core_record (scope, key);
