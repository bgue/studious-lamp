CREATE TABLE IF NOT EXISTS cur_thread_message (
  message_id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  seq INTEGER NOT NULL,
  author TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'message',
  body TEXT NOT NULL,
  mentions_json TEXT NOT NULL DEFAULT '{}',
  record_refs_json TEXT NOT NULL DEFAULT '{}',
  posted_at TEXT NOT NULL,
  edit_count INTEGER NOT NULL DEFAULT 0,
  retracted INTEGER NOT NULL DEFAULT 0,
  retract_reason TEXT,
  dispatch_json TEXT
);

CREATE INDEX IF NOT EXISTS ix_cur_thread_message_record_id ON cur_thread_message (record_id);

CREATE INDEX IF NOT EXISTS ix_cur_thread_message_record_seq ON cur_thread_message (record_id, seq);
