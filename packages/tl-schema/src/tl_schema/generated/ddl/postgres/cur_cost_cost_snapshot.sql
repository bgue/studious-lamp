CREATE TABLE IF NOT EXISTS cur_cost_cost_snapshot (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  period TEXT COLLATE "C" NOT NULL,
  revision BIGINT NOT NULL,
  as_of TEXT COLLATE "C" NOT NULL,
  currency TEXT COLLATE "C",
  source_name TEXT COLLATE "C",
  source_sha256 TEXT COLLATE "C",
  row_count BIGINT NOT NULL,
  new_code_count BIGINT NOT NULL,
  revised_code_count BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_cost_cost_snapshot_scope_period_revision ON cur_cost_cost_snapshot (scope, period, revision);

CREATE INDEX IF NOT EXISTS ix_cur_cost_cost_snapshot_scope_period ON cur_cost_cost_snapshot (scope, period, revision);
