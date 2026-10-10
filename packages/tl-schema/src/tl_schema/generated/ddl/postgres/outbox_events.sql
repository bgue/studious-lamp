CREATE TABLE IF NOT EXISTS outbox_events (
  seq BIGINT PRIMARY KEY,
  event_id TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  event_type TEXT COLLATE "C" NOT NULL,
  schema_version BIGINT NOT NULL DEFAULT 1,
  stream_id TEXT COLLATE "C" NOT NULL,
  stream_type TEXT COLLATE "C" NOT NULL,
  stream_version BIGINT NOT NULL,
  subject_id TEXT COLLATE "C" NOT NULL,
  subject_type TEXT COLLATE "C",
  subject_key TEXT COLLATE "C",
  subject_version BIGINT,
  actor TEXT COLLATE "C" NOT NULL,
  source TEXT COLLATE "C" NOT NULL,
  recorded_at TEXT COLLATE "C" NOT NULL,
  correlation_id TEXT COLLATE "C" NOT NULL,
  changed_fields_json JSONB NOT NULL DEFAULT '{}',
  from_state TEXT COLLATE "C",
  to_state TEXT COLLATE "C",
  related_ids_json JSONB NOT NULL DEFAULT '{}',
  link_relations_json JSONB NOT NULL DEFAULT '{}',
  file_slot TEXT COLLATE "C",
  hashtags_json JSONB NOT NULL DEFAULT '{}',
  data_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_outbox_events_scope ON outbox_events (scope);

CREATE INDEX IF NOT EXISTS ix_outbox_events_subject_id ON outbox_events (subject_id);
