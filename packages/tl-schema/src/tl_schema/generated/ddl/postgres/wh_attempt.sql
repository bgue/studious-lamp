CREATE TABLE IF NOT EXISTS wh_attempt (
  attempt_id TEXT COLLATE "C" PRIMARY KEY,
  delivery_id TEXT COLLATE "C" NOT NULL,
  subscription_id TEXT COLLATE "C" NOT NULL,
  attempt BIGINT NOT NULL,
  started_at TEXT COLLATE "C" NOT NULL,
  latency_ms BIGINT NOT NULL,
  status BIGINT,
  outcome TEXT COLLATE "C" NOT NULL,
  error TEXT COLLATE "C",
  response_excerpt TEXT COLLATE "C"
);

CREATE INDEX IF NOT EXISTS ix_wh_attempt_delivery_id ON wh_attempt (delivery_id);

CREATE INDEX IF NOT EXISTS ix_wh_attempt_subscription_id ON wh_attempt (subscription_id);
