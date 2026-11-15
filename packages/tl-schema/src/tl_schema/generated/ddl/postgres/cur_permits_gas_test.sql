CREATE TABLE IF NOT EXISTS cur_permits_gas_test (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  permit_id TEXT COLLATE "C" NOT NULL,
  taken_at TIMESTAMPTZ NOT NULL,
  tester TEXT COLLATE "C" NOT NULL,
  instrument_text TEXT COLLATE "C",
  o2_pct NUMERIC,
  lel_pct NUMERIC,
  h2s_ppm NUMERIC,
  co_ppm NUMERIC,
  result TEXT COLLATE "C" NOT NULL,
  note TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_permits_gas_test_permit ON cur_permits_gas_test (permit_id);

CREATE INDEX IF NOT EXISTS ix_cur_permits_gas_test_taken_at ON cur_permits_gas_test (taken_at);
