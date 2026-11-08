CREATE TABLE IF NOT EXISTS cur_awp_scope_item (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  commodity TEXT COLLATE "C" NOT NULL,
  description_text TEXT COLLATE "C",
  qty TEXT COLLATE "C",
  uom TEXT COLLATE "C",
  est_hours TEXT COLLATE "C",
  cwp_id TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_scope_item_scope_cwp ON cur_awp_scope_item (scope, cwp_id);
