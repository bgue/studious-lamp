CREATE TABLE IF NOT EXISTS int_delivery (
  delivery_id TEXT PRIMARY KEY,
  endpoint_id TEXT NOT NULL,
  endpoint_version INTEGER NOT NULL,
  scope TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'queued',
  object_key TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  payload_size INTEGER NOT NULL,
  corrected_object_key TEXT,
  received_at TEXT NOT NULL,
  finished_at TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  error_message TEXT,
  command_count INTEGER
);

CREATE INDEX IF NOT EXISTS ix_int_delivery_endpoint_state ON int_delivery (endpoint_id, state);

CREATE INDEX IF NOT EXISTS ix_int_delivery_received ON int_delivery (received_at);
