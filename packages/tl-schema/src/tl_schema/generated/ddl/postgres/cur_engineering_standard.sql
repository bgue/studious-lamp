CREATE TABLE IF NOT EXISTS cur_engineering_standard (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  label TEXT COLLATE "C" NOT NULL,
  definition TEXT COLLATE "C",
  edition TEXT COLLATE "C" NOT NULL,
  owner TEXT COLLATE "C",
  adoption TEXT COLLATE "C" NOT NULL DEFAULT 'default',
  value_list_policy TEXT COLLATE "C",
  effective_from TEXT COLLATE "C",
  effective_to TEXT COLLATE "C",
  lifecycle TEXT COLLATE "C" NOT NULL DEFAULT 'active',
  superseded_by TEXT COLLATE "C",
  data_json JSONB NOT NULL DEFAULT '{}',
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_engineering_standard_scope_kind_code_edition ON cur_engineering_standard (scope, kind, code, edition);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_standard_scope_kind_code ON cur_engineering_standard (scope, kind, code);
