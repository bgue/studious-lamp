CREATE TABLE IF NOT EXISTS sched_relationship (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  snapshot_id TEXT COLLATE "C" NOT NULL,
  pred_activity_id TEXT COLLATE "C" NOT NULL,
  succ_activity_id TEXT COLLATE "C" NOT NULL,
  relationship_type TEXT COLLATE "C" NOT NULL,
  lag_hr DOUBLE PRECISION NOT NULL,
  seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_relationship_snapshot_pred ON sched_relationship (snapshot_id, pred_activity_id);

CREATE INDEX IF NOT EXISTS ix_sched_relationship_snapshot_succ ON sched_relationship (snapshot_id, succ_activity_id);
