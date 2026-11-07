CREATE TABLE IF NOT EXISTS cur_awp_cwp_allocation (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  cwp_id TEXT NOT NULL,
  wbs_node_id TEXT NOT NULL,
  percent TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_cwp_allocation_cwp ON cur_awp_cwp_allocation (cwp_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_cwp_allocation_wbs_node ON cur_awp_cwp_allocation (wbs_node_id);
