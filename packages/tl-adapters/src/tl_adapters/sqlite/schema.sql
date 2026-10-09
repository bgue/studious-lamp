CREATE TABLE IF NOT EXISTS events (
  seq            INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id       TEXT NOT NULL UNIQUE,
  stream_id      TEXT NOT NULL,
  stream_type    TEXT NOT NULL,
  stream_version INTEGER NOT NULL,
  event_type     TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  scope          TEXT NOT NULL,
  payload        TEXT NOT NULL,
  actor          TEXT NOT NULL,
  recorded_at    TEXT NOT NULL,
  effective_at   TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  causation_id   TEXT,
  source         TEXT NOT NULL,
  prev_hash      TEXT,
  hash           TEXT NOT NULL,
  UNIQUE (stream_id, stream_version)
);
CREATE INDEX IF NOT EXISTS ix_events_scope_seq ON events(scope, seq);
CREATE TRIGGER IF NOT EXISTS trg_events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
