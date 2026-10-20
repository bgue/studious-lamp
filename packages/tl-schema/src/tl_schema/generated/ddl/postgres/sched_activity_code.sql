CREATE TABLE IF NOT EXISTS sched_activity_code (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  snapshot_id TEXT COLLATE "C" NOT NULL,
  activity_id TEXT COLLATE "C" NOT NULL,
  code_type TEXT COLLATE "C" NOT NULL,
  code_value TEXT COLLATE "C" NOT NULL,
  code_name TEXT COLLATE "C" NOT NULL,
  seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_activity_code_snapshot_activity ON sched_activity_code (snapshot_id, activity_id);
