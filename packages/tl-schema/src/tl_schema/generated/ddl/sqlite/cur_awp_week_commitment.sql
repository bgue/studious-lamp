CREATE TABLE IF NOT EXISTS cur_awp_week_commitment (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  plan_id TEXT NOT NULL,
  iwp_id TEXT NOT NULL,
  foreman TEXT NOT NULL,
  committed_hours TEXT NOT NULL,
  outcome TEXT,
  miss_reason TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_awp_week_commitment_plan_iwp ON cur_awp_week_commitment (plan_id, iwp_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_week_commitment_iwp ON cur_awp_week_commitment (iwp_id);
