CREATE TABLE IF NOT EXISTS int_replay (
  replay_id TEXT PRIMARY KEY,
  endpoint_id TEXT NOT NULL,
  seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_int_replay_seen ON int_replay (seen_at);
