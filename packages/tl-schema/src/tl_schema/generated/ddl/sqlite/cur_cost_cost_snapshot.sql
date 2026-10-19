CREATE TABLE IF NOT EXISTS cur_cost_cost_snapshot (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  period TEXT NOT NULL,
  revision INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  currency TEXT,
  source_name TEXT,
  source_sha256 TEXT,
  row_count INTEGER NOT NULL,
  new_code_count INTEGER NOT NULL,
  revised_code_count INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_cost_cost_snapshot_scope_period_revision ON cur_cost_cost_snapshot (scope, period, revision);

CREATE INDEX IF NOT EXISTS ix_cur_cost_cost_snapshot_scope_period ON cur_cost_cost_snapshot (scope, period, revision);
