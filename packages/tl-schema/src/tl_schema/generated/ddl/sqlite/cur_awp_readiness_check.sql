CREATE TABLE IF NOT EXISTS cur_awp_readiness_check (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  iwp_id TEXT NOT NULL,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  state TEXT NOT NULL,
  detail TEXT,
  count_ok INTEGER,
  count_total INTEGER,
  resolve_via_json TEXT,
  as_of_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_readiness_check_iwp ON cur_awp_readiness_check (iwp_id);
