CREATE TABLE IF NOT EXISTS wh_delivery (
  delivery_id TEXT PRIMARY KEY,
  subscription_id TEXT NOT NULL,
  dedupe_key TEXT NOT NULL,
  seq BIGINT NOT NULL,
  event_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'live',
  status TEXT NOT NULL DEFAULT 'pending',
  body TEXT NOT NULL,
  attempts BIGINT NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  next_attempt_at TEXT NOT NULL,
  lease_until TEXT,
  lease_owner TEXT,
  last_status BIGINT,
  last_error TEXT,
  delivered_at TEXT,
  dead_at TEXT,
  dead_reason TEXT,
  replay_of TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_wh_delivery_subscription_dedupe ON wh_delivery (subscription_id, dedupe_key);

CREATE INDEX IF NOT EXISTS ix_wh_delivery_subscription_id ON wh_delivery (subscription_id);

CREATE INDEX IF NOT EXISTS ix_wh_delivery_status ON wh_delivery (status);
