CREATE TABLE IF NOT EXISTS cur_permits_isolation (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  point_text TEXT NOT NULL,
  point_record_id TEXT,
  energy TEXT NOT NULL,
  method TEXT,
  lock_number TEXT,
  tag_number TEXT,
  applied_by TEXT,
  applied_at TEXT,
  verified_by TEXT,
  verified_at TEXT,
  removed_by TEXT,
  removed_at TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_permits_isolation_point_record ON cur_permits_isolation (point_record_id);
