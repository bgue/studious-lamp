CREATE TABLE IF NOT EXISTS wh_secret (
  secret_id TEXT COLLATE "C" PRIMARY KEY,
  subscription_id TEXT COLLATE "C" NOT NULL,
  secret TEXT COLLATE "C" NOT NULL,
  state TEXT COLLATE "C" NOT NULL DEFAULT 'active',
  created_at TEXT COLLATE "C" NOT NULL,
  expires_at TEXT COLLATE "C"
);

CREATE INDEX IF NOT EXISTS ix_wh_secret_subscription_id ON wh_secret (subscription_id);
