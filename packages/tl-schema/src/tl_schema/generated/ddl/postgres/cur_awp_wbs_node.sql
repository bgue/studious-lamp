CREATE TABLE IF NOT EXISTS cur_awp_wbs_node (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  parent_id TEXT COLLATE "C",
  depth BIGINT NOT NULL,
  position BIGINT NOT NULL,
  retired BOOLEAN NOT NULL DEFAULT FALSE,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_awp_wbs_node_scope_code ON cur_awp_wbs_node (scope, code);

CREATE INDEX IF NOT EXISTS ix_cur_awp_wbs_node_scope_code ON cur_awp_wbs_node (scope, code);

CREATE INDEX IF NOT EXISTS ix_cur_awp_wbs_node_scope_parent ON cur_awp_wbs_node (scope, parent_id, position);
