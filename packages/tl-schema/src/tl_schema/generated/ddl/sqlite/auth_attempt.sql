CREATE TABLE IF NOT EXISTS auth_attempt (
  username_key TEXT PRIMARY KEY,
  failed_count INTEGER NOT NULL DEFAULT 0,
  window_started_at TEXT NOT NULL,
  last_failed_at TEXT NOT NULL,
  lock_level INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT
);
