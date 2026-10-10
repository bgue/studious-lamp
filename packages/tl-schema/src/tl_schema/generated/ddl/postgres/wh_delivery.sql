CREATE TABLE IF NOT EXISTS wh_delivery (
  delivery_id TEXT COLLATE "C" PRIMARY KEY,
  subscription_id TEXT COLLATE "C" NOT NULL,
  dedupe_key TEXT COLLATE "C" NOT NULL,
  seq BIGINT NOT NULL,
  event_id TEXT COLLATE "C" NOT NULL,
  subject_id TEXT COLLATE "C" NOT NULL,
  origin TEXT COLLATE "C" NOT NULL DEFAULT 'live',
  status TEXT COLLATE "C" NOT NULL DEFAULT 'pending',
  body TEXT COLLATE "C" NOT NULL,
  attempts BIGINT NOT NULL DEFAULT 0,
  created_at TEXT COLLATE "C" NOT NULL,
  next_attempt_at TEXT COLLATE "C" NOT NULL,
  lease_until TEXT COLLATE "C",
  lease_owner TEXT COLLATE "C",
  last_status BIGINT,
  last_error TEXT COLLATE "C",
  delivered_at TEXT COLLATE "C",
  dead_at TEXT COLLATE "C",
  dead_reason TEXT COLLATE "C",
  replay_of TEXT COLLATE "C"
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_wh_delivery_subscription_dedupe ON wh_delivery (subscription_id, dedupe_key);

CREATE INDEX IF NOT EXISTS ix_wh_delivery_subscription_id ON wh_delivery (subscription_id);

CREATE INDEX IF NOT EXISTS ix_wh_delivery_status ON wh_delivery (status);
