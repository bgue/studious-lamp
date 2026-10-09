CREATE TABLE IF NOT EXISTS wh_attempt (
  attempt_id TEXT PRIMARY KEY,
  delivery_id TEXT NOT NULL,
  subscription_id TEXT NOT NULL,
  attempt BIGINT NOT NULL,
  started_at TEXT NOT NULL,
  latency_ms BIGINT NOT NULL,
  status BIGINT,
  outcome TEXT NOT NULL,
  error TEXT,
  response_excerpt TEXT
);

CREATE INDEX IF NOT EXISTS ix_wh_attempt_delivery_id ON wh_attempt (delivery_id);

CREATE INDEX IF NOT EXISTS ix_wh_attempt_subscription_id ON wh_attempt (subscription_id);
