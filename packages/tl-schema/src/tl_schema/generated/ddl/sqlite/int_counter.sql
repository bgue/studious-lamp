CREATE TABLE IF NOT EXISTS int_counter (
  counter_id TEXT PRIMARY KEY,
  endpoint_id TEXT NOT NULL,
  code TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  last_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_int_counter_endpoint_id ON int_counter (endpoint_id);
