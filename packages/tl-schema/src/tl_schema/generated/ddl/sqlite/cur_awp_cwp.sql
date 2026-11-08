CREATE TABLE IF NOT EXISTS cur_awp_cwp (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  discipline TEXT NOT NULL,
  cwa_id TEXT,
  planned_start TEXT,
  planned_finish TEXT,
  budget_hours TEXT,
  quantities_json TEXT,
  contractor_text TEXT,
  assigned_party TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_cwp_scope_cwa ON cur_awp_cwp (scope, cwa_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_cwp_scope_discipline ON cur_awp_cwp (scope, discipline);
