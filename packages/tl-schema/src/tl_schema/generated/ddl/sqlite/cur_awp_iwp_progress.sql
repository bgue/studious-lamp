CREATE TABLE IF NOT EXISTS cur_awp_iwp_progress (
  iwp_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  earned_pct TEXT NOT NULL,
  edition TEXT NOT NULL,
  as_of_seq INTEGER NOT NULL,
  manual_json TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_iwp_progress_scope ON cur_awp_iwp_progress (scope);
