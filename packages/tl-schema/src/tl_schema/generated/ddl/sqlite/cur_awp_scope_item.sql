CREATE TABLE IF NOT EXISTS cur_awp_scope_item (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  commodity TEXT NOT NULL,
  description_text TEXT,
  qty TEXT,
  uom TEXT,
  est_hours TEXT,
  cwp_id TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_scope_item_scope_cwp ON cur_awp_scope_item (scope, cwp_id);
