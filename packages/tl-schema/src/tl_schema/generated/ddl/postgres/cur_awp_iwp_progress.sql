CREATE TABLE IF NOT EXISTS cur_awp_iwp_progress (
  iwp_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  earned_pct TEXT COLLATE "C" NOT NULL,
  edition TEXT COLLATE "C" NOT NULL,
  as_of_seq BIGINT NOT NULL,
  manual_json JSONB,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_iwp_progress_scope ON cur_awp_iwp_progress (scope);
