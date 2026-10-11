CREATE TABLE IF NOT EXISTS tl_body_quarantine (
  record_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  type_name TEXT NOT NULL,
  uri TEXT NOT NULL,
  expected_hash TEXT NOT NULL,
  actual_hash TEXT,
  reason TEXT NOT NULL,
  detected_at TEXT NOT NULL
);
