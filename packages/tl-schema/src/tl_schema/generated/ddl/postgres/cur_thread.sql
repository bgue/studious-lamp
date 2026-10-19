CREATE TABLE IF NOT EXISTS cur_thread (
  record_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  message_count BIGINT NOT NULL DEFAULT 0,
  created_by TEXT COLLATE "C" NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  last_message_at TIMESTAMPTZ NOT NULL,
  last_seq BIGINT NOT NULL,
  version BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_thread_scope ON cur_thread (scope);
