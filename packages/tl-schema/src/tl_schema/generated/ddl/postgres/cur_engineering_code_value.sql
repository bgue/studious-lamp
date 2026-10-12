CREATE TABLE IF NOT EXISTS cur_engineering_code_value (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code_list TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  label TEXT COLLATE "C" NOT NULL,
  meaning TEXT COLLATE "C",
  crosswalk TEXT COLLATE "C",
  origin TEXT COLLATE "C" NOT NULL,
  sort_order BIGINT NOT NULL DEFAULT 0,
  effective_from TEXT COLLATE "C",
  effective_to TEXT COLLATE "C",
  lifecycle TEXT COLLATE "C" NOT NULL DEFAULT 'active',
  superseded_by TEXT COLLATE "C",
  attributes_json JSONB NOT NULL DEFAULT '{}',
  edition TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_engineering_code_value_scope_list_code ON cur_engineering_code_value (scope, code_list, code);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_code_value_scope_list_order ON cur_engineering_code_value (scope, code_list, sort_order, code);
