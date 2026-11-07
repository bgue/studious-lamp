CREATE TABLE IF NOT EXISTS cur_awp_iwp (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  discipline TEXT COLLATE "C" NOT NULL,
  cwp_id TEXT COLLATE "C",
  planned_start TEXT COLLATE "C",
  planned_finish TEXT COLLATE "C",
  foreman TEXT COLLATE "C",
  estimated_hours TEXT COLLATE "C",
  crew_text TEXT COLLATE "C",
  signoffs_json JSONB,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_iwp_scope_cwp ON cur_awp_iwp (scope, cwp_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_iwp_scope_discipline ON cur_awp_iwp (scope, discipline);
