CREATE TABLE IF NOT EXISTS outbox_events (
  seq BIGINT PRIMARY KEY,
  event_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  event_type TEXT NOT NULL,
  schema_version BIGINT NOT NULL DEFAULT 1,
  stream_id TEXT NOT NULL,
  stream_type TEXT NOT NULL,
  stream_version BIGINT NOT NULL,
  subject_id TEXT NOT NULL,
  subject_type TEXT,
  subject_key TEXT,
  subject_version BIGINT,
  actor TEXT NOT NULL,
  source TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  changed_fields_json JSONB NOT NULL DEFAULT '{}',
  from_state TEXT,
  to_state TEXT,
  related_ids_json JSONB NOT NULL DEFAULT '{}',
  link_relations_json JSONB NOT NULL DEFAULT '{}',
  file_slot TEXT,
  hashtags_json JSONB NOT NULL DEFAULT '{}',
  data_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_outbox_events_scope ON outbox_events (scope);

CREATE INDEX IF NOT EXISTS ix_outbox_events_subject_id ON outbox_events (subject_id);
