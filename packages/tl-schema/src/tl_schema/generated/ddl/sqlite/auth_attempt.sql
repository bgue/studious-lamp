CREATE TABLE IF NOT EXISTS auth_attempt (
  username_key TEXT PRIMARY KEY,
  failed_count INTEGER NOT NULL DEFAULT 0,
  window_started_at TEXT NOT NULL,
  last_failed_at TEXT NOT NULL,
  locked_until TEXT
);

CREATE INDEX IF NOT EXISTS ix_auth_attempt_last_failed_at ON auth_attempt (last_failed_at);
