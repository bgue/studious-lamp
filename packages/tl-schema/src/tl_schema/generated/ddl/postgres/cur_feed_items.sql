CREATE TABLE IF NOT EXISTS cur_feed_items (
  item_id TEXT PRIMARY KEY,
  item_type TEXT NOT NULL,
  scope TEXT NOT NULL,
  actor TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  seq BIGINT NOT NULL,
  summary TEXT NOT NULL,
  importance TEXT NOT NULL DEFAULT 'normal',
  base_importance TEXT NOT NULL DEFAULT 'normal',
  event_type TEXT,
  event_count BIGINT NOT NULL DEFAULT 1,
  first_us BIGINT,
  first_seq BIGINT,
  open_scope TEXT,
  retracted BOOLEAN NOT NULL DEFAULT FALSE,
  retract_reason TEXT,
  edit_count BIGINT NOT NULL DEFAULT 0,
  reactions_json JSONB NOT NULL DEFAULT '{}',
  version BIGINT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_feed_items_open_scope ON cur_feed_items (open_scope);

CREATE INDEX IF NOT EXISTS ix_cur_feed_items_scope ON cur_feed_items (scope);

CREATE INDEX IF NOT EXISTS ix_cur_feed_items_seq ON cur_feed_items (seq);
