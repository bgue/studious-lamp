CREATE TABLE IF NOT EXISTS int_delivery (
  delivery_id TEXT COLLATE "C" PRIMARY KEY,
  endpoint_id TEXT COLLATE "C" NOT NULL,
  endpoint_version BIGINT NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  state TEXT COLLATE "C" NOT NULL DEFAULT 'queued',
  object_key TEXT COLLATE "C" NOT NULL,
  payload_sha256 TEXT COLLATE "C" NOT NULL,
  payload_size BIGINT NOT NULL,
  corrected_object_key TEXT COLLATE "C",
  received_at TEXT COLLATE "C" NOT NULL,
  finished_at TEXT COLLATE "C",
  attempts BIGINT NOT NULL DEFAULT 0,
  error_code TEXT COLLATE "C",
  error_message TEXT COLLATE "C",
  command_count BIGINT
);

CREATE INDEX IF NOT EXISTS ix_int_delivery_endpoint_state ON int_delivery (endpoint_id, state);

CREATE INDEX IF NOT EXISTS ix_int_delivery_received ON int_delivery (received_at);
