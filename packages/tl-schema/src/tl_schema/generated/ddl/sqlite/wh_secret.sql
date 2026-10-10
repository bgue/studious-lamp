CREATE TABLE IF NOT EXISTS wh_secret (
  secret_id TEXT PRIMARY KEY,
  subscription_id TEXT NOT NULL,
  secret TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  expires_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_wh_secret_subscription_id ON wh_secret (subscription_id);
