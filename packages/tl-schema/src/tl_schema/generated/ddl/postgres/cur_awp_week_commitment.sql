CREATE TABLE IF NOT EXISTS cur_awp_week_commitment (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  plan_id TEXT COLLATE "C" NOT NULL,
  iwp_id TEXT COLLATE "C" NOT NULL,
  foreman TEXT COLLATE "C" NOT NULL,
  committed_hours TEXT COLLATE "C" NOT NULL,
  outcome TEXT COLLATE "C",
  miss_reason TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_awp_week_commitment_plan_iwp ON cur_awp_week_commitment (plan_id, iwp_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_week_commitment_iwp ON cur_awp_week_commitment (iwp_id);
