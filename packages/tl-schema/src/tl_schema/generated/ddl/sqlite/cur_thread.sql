CREATE TABLE IF NOT EXISTS cur_thread (
  record_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  message_count INTEGER NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_message_at TEXT NOT NULL,
  last_seq INTEGER NOT NULL,
  version INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_thread_scope ON cur_thread (scope);
