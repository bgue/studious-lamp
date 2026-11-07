CREATE TABLE IF NOT EXISTS cur_awp_cwp (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  discipline TEXT COLLATE "C" NOT NULL,
  cwa_id TEXT COLLATE "C",
  planned_start TEXT COLLATE "C",
  planned_finish TEXT COLLATE "C",
  budget_hours TEXT COLLATE "C",
  quantities_json JSONB,
  contractor_text TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_cwp_scope_cwa ON cur_awp_cwp (scope, cwa_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_cwp_scope_discipline ON cur_awp_cwp (scope, discipline);
