CREATE TABLE IF NOT EXISTS cur_numbering (
  counter_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  pattern TEXT COLLATE "C" NOT NULL,
  prefix TEXT COLLATE "C" NOT NULL,
  last_sequence BIGINT NOT NULL,
  last_key TEXT COLLATE "C" NOT NULL,
  last_record_id TEXT COLLATE "C",
  allocations BIGINT NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
