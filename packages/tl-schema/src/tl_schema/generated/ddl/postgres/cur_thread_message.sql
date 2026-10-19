CREATE TABLE IF NOT EXISTS cur_thread_message (
  message_id TEXT COLLATE "C" PRIMARY KEY,
  record_id TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  seq BIGINT NOT NULL,
  author TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL DEFAULT 'message',
  body TEXT COLLATE "C" NOT NULL,
  mentions_json JSONB NOT NULL DEFAULT '{}',
  record_refs_json JSONB NOT NULL DEFAULT '{}',
  posted_at TIMESTAMPTZ NOT NULL,
  edit_count BIGINT NOT NULL DEFAULT 0,
  retracted BOOLEAN NOT NULL DEFAULT FALSE,
  retract_reason TEXT COLLATE "C",
  dispatch_json JSONB
);

CREATE INDEX IF NOT EXISTS ix_cur_thread_message_record_id ON cur_thread_message (record_id);

CREATE INDEX IF NOT EXISTS ix_cur_thread_message_record_seq ON cur_thread_message (record_id, seq);
