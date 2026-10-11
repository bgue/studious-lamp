CREATE TABLE IF NOT EXISTS cur_core_record_body (
  record_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  type_name TEXT NOT NULL,
  uri TEXT NOT NULL,
  hash TEXT NOT NULL,
  body_size INTEGER NOT NULL,
  schema_hash TEXT NOT NULL,
  body_versions INTEGER NOT NULL,
  last_seq INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_core_record_body_type_name ON cur_core_record_body (type_name);
