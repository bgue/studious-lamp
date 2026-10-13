CREATE TABLE IF NOT EXISTS cur_engineering_code_value (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code_list TEXT NOT NULL,
  code TEXT NOT NULL,
  label TEXT NOT NULL,
  meaning TEXT,
  crosswalk TEXT,
  origin TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  effective_from TEXT,
  effective_to TEXT,
  lifecycle TEXT NOT NULL DEFAULT 'active',
  superseded_by TEXT,
  attributes_json TEXT NOT NULL DEFAULT '{}',
  edition TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_engineering_code_value_scope_list_code ON cur_engineering_code_value (scope, code_list, code);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_code_value_scope_list_order ON cur_engineering_code_value (scope, code_list, sort_order, code);
