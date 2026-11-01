CREATE TABLE IF NOT EXISTS cur_awp_wbs_allocation (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  node_id TEXT NOT NULL,
  cost_code_id TEXT NOT NULL,
  percent TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_wbs_allocation_cost_code ON cur_awp_wbs_allocation (cost_code_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_wbs_allocation_node ON cur_awp_wbs_allocation (node_id);
