CREATE TABLE IF NOT EXISTS cur_awp_iwp_closeout (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  iwp_id TEXT NOT NULL,
  actual_hours TEXT,
  remaining_punch INTEGER,
  feedback TEXT,
  actuals_file_id TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_iwp_closeout_scope_iwp ON cur_awp_iwp_closeout (scope, iwp_id);
