CREATE TABLE IF NOT EXISTS int_counter (
  counter_id TEXT COLLATE "C" PRIMARY KEY,
  endpoint_id TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  count BIGINT NOT NULL DEFAULT 0,
  last_at TEXT COLLATE "C" NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_int_counter_endpoint_id ON int_counter (endpoint_id);
