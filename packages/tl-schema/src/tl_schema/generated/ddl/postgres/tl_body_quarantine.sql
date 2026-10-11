CREATE TABLE IF NOT EXISTS tl_body_quarantine (
  record_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  type_name TEXT COLLATE "C" NOT NULL,
  uri TEXT COLLATE "C" NOT NULL,
  expected_hash TEXT COLLATE "C" NOT NULL,
  actual_hash TEXT COLLATE "C",
  reason TEXT COLLATE "C" NOT NULL,
  detected_at TIMESTAMPTZ NOT NULL
);
