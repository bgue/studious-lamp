CREATE TABLE IF NOT EXISTS cur_schedule_activity_ref (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  schedule_id TEXT COLLATE "C" NOT NULL,
  schedule_code TEXT COLLATE "C" NOT NULL,
  activity_id TEXT COLLATE "C" NOT NULL,
  first_snapshot_id TEXT COLLATE "C" NOT NULL,
  first_snapshot_number BIGINT NOT NULL,
  present BOOLEAN NOT NULL DEFAULT TRUE,
  last_seen_snapshot_id TEXT COLLATE "C",
  last_seen_number BIGINT,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_schedule_activity_ref_schedule_activity ON cur_schedule_activity_ref (schedule_id, activity_id);

CREATE INDEX IF NOT EXISTS ix_cur_schedule_activity_ref_scope_schedule ON cur_schedule_activity_ref (scope, schedule_id);
