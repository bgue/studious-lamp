CREATE TABLE IF NOT EXISTS telemetry_need (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  need_id TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C",
  recorded_at TEXT COLLATE "C" NOT NULL,
  request_kind TEXT COLLATE "C" NOT NULL,
  trigger TEXT COLLATE "C" NOT NULL,
  record_type TEXT COLLATE "C" NOT NULL,
  record_id TEXT COLLATE "C",
  viewer_role TEXT COLLATE "C" NOT NULL,
  provider_kind TEXT COLLATE "C",
  duration_ms BIGINT,
  outcome TEXT COLLATE "C" NOT NULL,
  why TEXT COLLATE "C"
);

CREATE INDEX IF NOT EXISTS ix_telemetry_need_need_id ON telemetry_need (need_id);

CREATE INDEX IF NOT EXISTS ix_telemetry_need_recorded_at ON telemetry_need (recorded_at);
