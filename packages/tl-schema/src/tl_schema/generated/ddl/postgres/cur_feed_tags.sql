CREATE TABLE IF NOT EXISTS cur_feed_tags (
  tag_row_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  kind TEXT NOT NULL,
  tag_text TEXT NOT NULL,
  tag_key TEXT NOT NULL,
  namespace TEXT,
  record_id TEXT,
  start_pos BIGINT NOT NULL,
  end_pos BIGINT NOT NULL,
  seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_feed_tags_item_id ON cur_feed_tags (item_id);

CREATE INDEX IF NOT EXISTS ix_cur_feed_tags_tag_key ON cur_feed_tags (tag_key);

CREATE INDEX IF NOT EXISTS ix_cur_feed_tags_record_id ON cur_feed_tags (record_id);
