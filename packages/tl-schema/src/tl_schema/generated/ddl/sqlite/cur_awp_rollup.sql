CREATE TABLE IF NOT EXISTS cur_awp_rollup (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  subject_kind TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  line TEXT NOT NULL,
  cost_code_id TEXT,
  measure TEXT NOT NULL,
  value TEXT NOT NULL,
  as_of_seq INTEGER NOT NULL,
  run_id TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_rollup_run ON cur_awp_rollup (run_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_rollup_subject ON cur_awp_rollup (scope, subject_kind, subject_id, measure);
