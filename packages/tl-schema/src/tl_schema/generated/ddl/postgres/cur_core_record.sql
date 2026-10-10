CREATE TABLE IF NOT EXISTS cur_core_record (
  id TEXT COLLATE "C" PRIMARY KEY,
  key TEXT COLLATE "C",
  type TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  title TEXT COLLATE "C" NOT NULL,
  description TEXT COLLATE "C",
  status TEXT COLLATE "C",
  psets_json JSONB NOT NULL DEFAULT '{}',
  voided BOOLEAN NOT NULL DEFAULT FALSE,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL,
  effective_schema_hash TEXT COLLATE "C",
  conformance TEXT COLLATE "C" NOT NULL DEFAULT 'ok',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_core_record_scope_key ON cur_core_record (scope, key);

CREATE INDEX IF NOT EXISTS ix_cur_core_record_scope_voided_created ON cur_core_record (scope, voided, created_at, id);

CREATE INDEX IF NOT EXISTS ix_cur_core_record_scope_voided_key_asc ON cur_core_record (scope, voided, (key IS NULL OR key = ''), key, id);

CREATE INDEX IF NOT EXISTS ix_cur_core_record_scope_voided_key_desc ON cur_core_record (scope, voided, (key IS NULL OR key = ''), key DESC, id);

CREATE INDEX IF NOT EXISTS ix_cur_core_record_scope_voided_updated ON cur_core_record (scope, voided, updated_at, id);
