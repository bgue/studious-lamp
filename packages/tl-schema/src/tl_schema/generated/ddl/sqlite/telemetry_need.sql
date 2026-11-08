CREATE TABLE IF NOT EXISTS telemetry_need (
  row_id TEXT PRIMARY KEY,
  need_id TEXT NOT NULL,
  scope TEXT,
  recorded_at TEXT NOT NULL,
  request_kind TEXT NOT NULL,
  trigger TEXT NOT NULL,
  record_type TEXT NOT NULL,
  record_id TEXT,
  viewer_role TEXT NOT NULL,
  provider_kind TEXT,
  duration_ms INTEGER,
  outcome TEXT NOT NULL,
  why TEXT
);

CREATE INDEX IF NOT EXISTS ix_telemetry_need_need_id ON telemetry_need (need_id);

CREATE INDEX IF NOT EXISTS ix_telemetry_need_recorded_at ON telemetry_need (recorded_at);
