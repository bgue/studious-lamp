CREATE TABLE IF NOT EXISTS cur_feed_tags (
  tag_row_id TEXT COLLATE "C" PRIMARY KEY,
  item_id TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  tag_text TEXT COLLATE "C" NOT NULL,
  tag_key TEXT COLLATE "C" NOT NULL,
  namespace TEXT COLLATE "C",
  record_id TEXT COLLATE "C",
  start_pos BIGINT NOT NULL,
  end_pos BIGINT NOT NULL,
  seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_feed_tags_item_id ON cur_feed_tags (item_id);

CREATE INDEX IF NOT EXISTS ix_cur_feed_tags_tag_key ON cur_feed_tags (tag_key);

CREATE INDEX IF NOT EXISTS ix_cur_feed_tags_record_id ON cur_feed_tags (record_id);
