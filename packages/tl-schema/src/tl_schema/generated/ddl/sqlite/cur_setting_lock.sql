CREATE TABLE IF NOT EXISTS cur_setting_lock (
  key TEXT PRIMARY KEY,
  locked INTEGER NOT NULL DEFAULT 0,
  bounds_json TEXT,
  reason TEXT NOT NULL,
  actor TEXT NOT NULL,
  seq INTEGER NOT NULL,
  version INTEGER NOT NULL,
  recorded_at TEXT NOT NULL
);
