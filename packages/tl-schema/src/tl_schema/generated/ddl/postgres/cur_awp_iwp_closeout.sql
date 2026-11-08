CREATE TABLE IF NOT EXISTS cur_awp_iwp_closeout (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  iwp_id TEXT COLLATE "C" NOT NULL,
  actual_hours TEXT COLLATE "C",
  remaining_punch BIGINT,
  feedback TEXT COLLATE "C",
  actuals_file_id TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_iwp_closeout_scope_iwp ON cur_awp_iwp_closeout (scope, iwp_id);
