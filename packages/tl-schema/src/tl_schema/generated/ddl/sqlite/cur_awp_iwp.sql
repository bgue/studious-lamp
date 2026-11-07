CREATE TABLE IF NOT EXISTS cur_awp_iwp (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  discipline TEXT NOT NULL,
  cwp_id TEXT,
  planned_start TEXT,
  planned_finish TEXT,
  foreman TEXT,
  estimated_hours TEXT,
  crew_text TEXT,
  signoffs_json TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_iwp_scope_cwp ON cur_awp_iwp (scope, cwp_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_iwp_scope_discipline ON cur_awp_iwp (scope, discipline);
