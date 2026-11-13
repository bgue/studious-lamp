CREATE TABLE IF NOT EXISTS cur_awp_weekly_plan (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  week TEXT NOT NULL,
  week_start TEXT NOT NULL,
  ppc TEXT,
  closed_at TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_weekly_plan_scope_week ON cur_awp_weekly_plan (scope, week);
