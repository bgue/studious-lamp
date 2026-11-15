CREATE TABLE IF NOT EXISTS cur_permits_isolation (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  point_text TEXT COLLATE "C" NOT NULL,
  point_record_id TEXT COLLATE "C",
  energy TEXT COLLATE "C" NOT NULL,
  method TEXT COLLATE "C",
  lock_number TEXT COLLATE "C",
  tag_number TEXT COLLATE "C",
  applied_by TEXT COLLATE "C",
  applied_at TIMESTAMPTZ,
  verified_by TEXT COLLATE "C",
  verified_at TIMESTAMPTZ,
  removed_by TEXT COLLATE "C",
  removed_at TIMESTAMPTZ,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_permits_isolation_point_record ON cur_permits_isolation (point_record_id);
