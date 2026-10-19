CREATE TABLE IF NOT EXISTS sched_udf_value (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  snapshot_id TEXT COLLATE "C" NOT NULL,
  activity_id TEXT COLLATE "C" NOT NULL,
  udf_name TEXT COLLATE "C" NOT NULL,
  udf_label TEXT COLLATE "C",
  value_type TEXT COLLATE "C" NOT NULL,
  value TEXT COLLATE "C" NOT NULL,
  seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_udf_value_snapshot_activity ON sched_udf_value (snapshot_id, activity_id);
