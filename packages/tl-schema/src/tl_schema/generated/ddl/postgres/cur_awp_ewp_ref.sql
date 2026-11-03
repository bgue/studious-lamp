CREATE TABLE IF NOT EXISTS cur_awp_ewp_ref (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  package_no TEXT COLLATE "C" NOT NULL,
  status_text TEXT COLLATE "C",
  forecast_date TEXT COLLATE "C",
  actual_date TEXT COLLATE "C",
  constraint_source BOOLEAN NOT NULL DEFAULT FALSE,
  source_system TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_awp_ewp_ref_scope_package_no ON cur_awp_ewp_ref (scope, package_no);
