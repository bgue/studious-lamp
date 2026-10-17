CREATE TABLE IF NOT EXISTS sched_calendar (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  calendar_id TEXT NOT NULL,
  name TEXT NOT NULL,
  day_hr REAL NOT NULL,
  week_hr REAL,
  month_hr REAL,
  year_hr REAL,
  is_default INTEGER NOT NULL,
  seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sched_calendar_snapshot ON sched_calendar (snapshot_id, seq);
