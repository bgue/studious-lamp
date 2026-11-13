CREATE TABLE IF NOT EXISTS cur_awp_weekly_plan (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  week TEXT COLLATE "C" NOT NULL,
  week_start TEXT COLLATE "C" NOT NULL,
  ppc TEXT COLLATE "C",
  closed_at TIMESTAMPTZ,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_weekly_plan_scope_week ON cur_awp_weekly_plan (scope, week);
