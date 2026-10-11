CREATE TABLE IF NOT EXISTS auth_attempt (
  username_key TEXT COLLATE "C" PRIMARY KEY,
  failed_count BIGINT NOT NULL DEFAULT 0,
  window_started_at TEXT COLLATE "C" NOT NULL,
  last_failed_at TEXT COLLATE "C" NOT NULL,
  locked_until TEXT COLLATE "C"
);

CREATE INDEX IF NOT EXISTS ix_auth_attempt_last_failed_at ON auth_attempt (last_failed_at);
