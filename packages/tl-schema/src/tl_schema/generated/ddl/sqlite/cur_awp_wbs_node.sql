CREATE TABLE IF NOT EXISTS cur_awp_wbs_node (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  parent_id TEXT,
  depth INTEGER NOT NULL,
  position INTEGER NOT NULL,
  retired INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_awp_wbs_node_scope_code ON cur_awp_wbs_node (scope, code);

CREATE INDEX IF NOT EXISTS ix_cur_awp_wbs_node_scope_code ON cur_awp_wbs_node (scope, code);

CREATE INDEX IF NOT EXISTS ix_cur_awp_wbs_node_scope_parent ON cur_awp_wbs_node (scope, parent_id, position);
