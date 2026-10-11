CREATE TABLE IF NOT EXISTS cur_core_type_registration (
  type_ref TEXT PRIMARY KEY,
  type_name TEXT NOT NULL,
  namespace TEXT NOT NULL,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  pset TEXT,
  location_uri TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  owner TEXT,
  status TEXT NOT NULL,
  storage_mode TEXT,
  index_fields_json TEXT,
  schema_hash TEXT,
  report_json TEXT,
  conflict_hash TEXT,
  reason TEXT,
  first_seq INTEGER NOT NULL,
  last_seq INTEGER NOT NULL,
  version_n INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_core_type_registration_type_name ON cur_core_type_registration (type_name);

CREATE INDEX IF NOT EXISTS ix_cur_core_type_registration_status ON cur_core_type_registration (status);
