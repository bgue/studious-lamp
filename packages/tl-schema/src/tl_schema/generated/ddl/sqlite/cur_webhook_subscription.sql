CREATE TABLE IF NOT EXISTS cur_webhook_subscription (
  subscription_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  name TEXT NOT NULL,
  owner TEXT NOT NULL,
  integration_app TEXT,
  target_url TEXT NOT NULL,
  filter_json TEXT NOT NULL DEFAULT '{}',
  payload_mode TEXT NOT NULL DEFAULT 'thin',
  event_schema_version TEXT NOT NULL DEFAULT 'v1',
  status TEXT NOT NULL DEFAULT 'active',
  disabled_reason TEXT,
  active_windows_json TEXT NOT NULL DEFAULT '{}',
  expires_at TEXT,
  current_secret_id TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_webhook_subscription_scope ON cur_webhook_subscription (scope);
