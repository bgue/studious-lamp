CREATE TABLE IF NOT EXISTS cur_numbering (
  counter_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  pattern TEXT NOT NULL,
  prefix TEXT NOT NULL,
  last_sequence INTEGER NOT NULL,
  last_key TEXT NOT NULL,
  last_record_id TEXT,
  allocations INTEGER NOT NULL,
  version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
