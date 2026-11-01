CREATE TABLE IF NOT EXISTS cur_awp_cwp_allocation (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  cwp_id TEXT COLLATE "C" NOT NULL,
  wbs_node_id TEXT COLLATE "C" NOT NULL,
  percent TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_cwp_allocation_cwp ON cur_awp_cwp_allocation (cwp_id);

CREATE INDEX IF NOT EXISTS ix_cur_awp_cwp_allocation_wbs_node ON cur_awp_cwp_allocation (wbs_node_id);
