CREATE TABLE IF NOT EXISTS cur_feed_items (
  item_id TEXT COLLATE "C" PRIMARY KEY,
  item_type TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  actor TEXT COLLATE "C" NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  seq BIGINT NOT NULL,
  summary TEXT COLLATE "C" NOT NULL,
  importance TEXT COLLATE "C" NOT NULL DEFAULT 'normal',
  base_importance TEXT COLLATE "C" NOT NULL DEFAULT 'normal',
  event_type TEXT COLLATE "C",
  event_count BIGINT NOT NULL DEFAULT 1,
  first_us BIGINT,
  first_seq BIGINT,
  open_scope TEXT COLLATE "C",
  retracted BOOLEAN NOT NULL DEFAULT FALSE,
  retract_reason TEXT COLLATE "C",
  edit_count BIGINT NOT NULL DEFAULT 0,
  reactions_json JSONB NOT NULL DEFAULT '{}',
  version BIGINT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_feed_items_open_scope ON cur_feed_items (open_scope);

CREATE INDEX IF NOT EXISTS ix_cur_feed_items_scope ON cur_feed_items (scope);

CREATE INDEX IF NOT EXISTS ix_cur_feed_items_seq ON cur_feed_items (seq);
