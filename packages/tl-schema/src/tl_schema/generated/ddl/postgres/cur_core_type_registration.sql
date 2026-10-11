CREATE TABLE IF NOT EXISTS cur_core_type_registration (
  type_ref TEXT COLLATE "C" PRIMARY KEY,
  type_name TEXT COLLATE "C" NOT NULL,
  namespace TEXT COLLATE "C" NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  version TEXT COLLATE "C" NOT NULL,
  pset TEXT COLLATE "C",
  location_uri TEXT COLLATE "C" NOT NULL,
  content_hash TEXT COLLATE "C" NOT NULL,
  owner TEXT COLLATE "C",
  status TEXT COLLATE "C" NOT NULL,
  storage_mode TEXT COLLATE "C",
  index_fields_json JSONB,
  schema_hash TEXT COLLATE "C",
  report_json JSONB,
  conflict_hash TEXT COLLATE "C",
  reason TEXT COLLATE "C",
  first_seq BIGINT NOT NULL,
  last_seq BIGINT NOT NULL,
  version_n BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_core_type_registration_type_name ON cur_core_type_registration (type_name);

CREATE INDEX IF NOT EXISTS ix_cur_core_type_registration_status ON cur_core_type_registration (status);
