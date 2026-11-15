CREATE TABLE IF NOT EXISTS cur_permits_gas_test (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  permit_id TEXT NOT NULL,
  taken_at TEXT NOT NULL,
  tester TEXT NOT NULL,
  instrument_text TEXT,
  o2_pct NUMERIC,
  lel_pct NUMERIC,
  h2s_ppm NUMERIC,
  co_ppm NUMERIC,
  result TEXT NOT NULL,
  note TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_permits_gas_test_permit ON cur_permits_gas_test (permit_id);

CREATE INDEX IF NOT EXISTS ix_cur_permits_gas_test_taken_at ON cur_permits_gas_test (taken_at);
