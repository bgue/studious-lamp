CREATE TABLE IF NOT EXISTS cur_feed_items (
  item_id TEXT PRIMARY KEY,
  item_type TEXT NOT NULL,
  scope TEXT NOT NULL,
  actor TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  seq INTEGER NOT NULL,
  summary TEXT NOT NULL,
  importance TEXT NOT NULL DEFAULT 'normal',
  base_importance TEXT NOT NULL DEFAULT 'normal',
  event_type TEXT,
  event_count INTEGER NOT NULL DEFAULT 1,
  first_us INTEGER,
  first_seq INTEGER,
  open_scope TEXT,
  retracted INTEGER NOT NULL DEFAULT 0,
  retract_reason TEXT,
  edit_count INTEGER NOT NULL DEFAULT 0,
  reactions_json TEXT NOT NULL DEFAULT '{}',
  version INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_feed_items_open_scope ON cur_feed_items (open_scope);

CREATE INDEX IF NOT EXISTS ix_cur_feed_items_scope ON cur_feed_items (scope);

CREATE INDEX IF NOT EXISTS ix_cur_feed_items_seq ON cur_feed_items (seq);
