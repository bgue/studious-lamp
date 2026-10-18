CREATE TABLE IF NOT EXISTS int_replay (
  replay_id TEXT COLLATE "C" PRIMARY KEY,
  endpoint_id TEXT COLLATE "C" NOT NULL,
  seen_at TEXT COLLATE "C" NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_int_replay_seen ON int_replay (seen_at);
