CREATE TABLE IF NOT EXISTS cur_numbering (
  counter_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  pattern TEXT NOT NULL,
  prefix TEXT NOT NULL,
  last_sequence BIGINT NOT NULL,
  last_key TEXT NOT NULL,
  last_record_id TEXT,
  allocations BIGINT NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
