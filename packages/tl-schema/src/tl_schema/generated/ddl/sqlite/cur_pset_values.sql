CREATE TABLE IF NOT EXISTS cur_pset_values (
  record_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  path TEXT NOT NULL,
  pset TEXT NOT NULL,
  property_name TEXT NOT NULL,
  layer TEXT NOT NULL,
  value_type TEXT NOT NULL,
  value_text TEXT,
  value_num REAL,
  value_bool INTEGER,
  value_json TEXT,
  unit TEXT,
  last_seq INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_pset_values_record_path ON cur_pset_values (record_id, path);

CREATE INDEX IF NOT EXISTS ix_cur_pset_values_record_id ON cur_pset_values (record_id);

CREATE INDEX IF NOT EXISTS ix_cur_pset_values_path ON cur_pset_values (path);
