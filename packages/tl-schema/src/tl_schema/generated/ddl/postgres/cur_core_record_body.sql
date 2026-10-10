CREATE TABLE IF NOT EXISTS cur_core_record_body (
  record_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  type_name TEXT COLLATE "C" NOT NULL,
  uri TEXT COLLATE "C" NOT NULL,
  hash TEXT COLLATE "C" NOT NULL,
  body_size BIGINT NOT NULL,
  schema_hash TEXT COLLATE "C" NOT NULL,
  body_versions BIGINT NOT NULL,
  last_seq BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_core_record_body_type_name ON cur_core_record_body (type_name);
