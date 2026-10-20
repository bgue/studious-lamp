CREATE TABLE IF NOT EXISTS sched_calendar (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  snapshot_id TEXT COLLATE "C" NOT NULL,
  calendar_id TEXT COLLATE "C" NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  day_hr DOUBLE PRECISION NOT NULL,
  week_hr DOUBLE PRECISION,
  month_hr DOUBLE PRECISION,
  year_hr DOUBLE PRECISION,
  is_default BOOLEAN NOT NULL,
  seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_calendar_snapshot ON sched_calendar (snapshot_id, seq);
