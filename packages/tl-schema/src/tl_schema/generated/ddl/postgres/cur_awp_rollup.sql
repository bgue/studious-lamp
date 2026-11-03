CREATE TABLE IF NOT EXISTS cur_awp_rollup (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  subject_kind TEXT COLLATE "C" NOT NULL,
  subject_id TEXT COLLATE "C" NOT NULL,
  line TEXT COLLATE "C" NOT NULL,
  cost_code_id TEXT COLLATE "C",
  measure TEXT COLLATE "C" NOT NULL,
  value TEXT COLLATE "C" NOT NULL,
  as_of_seq BIGINT NOT NULL,
  run_id TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_rollup_run ON cur_awp_rollup (run_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_rollup_subject ON cur_awp_rollup (scope, subject_kind, subject_id, measure);
