CREATE TABLE IF NOT EXISTS cur_pset_values (
  record_id TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  path TEXT COLLATE "C" NOT NULL,
  pset TEXT COLLATE "C" NOT NULL,
  property_name TEXT COLLATE "C" NOT NULL,
  layer TEXT COLLATE "C" NOT NULL,
  value_type TEXT COLLATE "C" NOT NULL,
  value_text TEXT COLLATE "C",
  value_num DOUBLE PRECISION,
  value_bool BOOLEAN,
  value_json JSONB,
  unit TEXT COLLATE "C",
  last_seq BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_pset_values_record_path ON cur_pset_values (record_id, path);

CREATE INDEX IF NOT EXISTS ix_cur_pset_values_record_id ON cur_pset_values (record_id);

CREATE INDEX IF NOT EXISTS ix_cur_pset_values_path ON cur_pset_values (path);
