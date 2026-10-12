CREATE TABLE IF NOT EXISTS cur_engineering_standard (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  kind TEXT NOT NULL,
  code TEXT NOT NULL,
  label TEXT NOT NULL,
  definition TEXT,
  edition TEXT NOT NULL,
  owner TEXT,
  adoption TEXT NOT NULL DEFAULT 'default',
  value_list_policy TEXT,
  effective_from TEXT,
  effective_to TEXT,
  lifecycle TEXT NOT NULL DEFAULT 'active',
  superseded_by TEXT,
  data_json TEXT NOT NULL DEFAULT '{}',
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_engineering_standard_scope_kind_code_edition ON cur_engineering_standard (scope, kind, code, edition);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_standard_scope_kind_code ON cur_engineering_standard (scope, kind, code);
