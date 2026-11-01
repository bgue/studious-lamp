CREATE TABLE IF NOT EXISTS cur_awp_pwp_ref (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  package_no TEXT NOT NULL,
  status_text TEXT,
  forecast_date TEXT,
  actual_date TEXT,
  constraint_source INTEGER NOT NULL DEFAULT 0,
  source_system TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_awp_pwp_ref_scope_package_no ON cur_awp_pwp_ref (scope, package_no);

CREATE INDEX IF NOT EXISTS ix_cur_awp_pwp_ref_scope_package ON cur_awp_pwp_ref (scope, package_no);
