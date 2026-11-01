CREATE TABLE IF NOT EXISTS cur_awp_wbs_allocation (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  node_id TEXT COLLATE "C" NOT NULL,
  cost_code_id TEXT COLLATE "C" NOT NULL,
  percent TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_wbs_allocation_cost_code ON cur_awp_wbs_allocation (cost_code_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_wbs_allocation_node ON cur_awp_wbs_allocation (node_id);
