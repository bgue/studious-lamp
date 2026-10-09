CREATE TABLE IF NOT EXISTS cur_webhook_subscription (
  subscription_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  name TEXT NOT NULL,
  owner TEXT NOT NULL,
  integration_app TEXT,
  target_url TEXT NOT NULL,
  filter_json JSONB NOT NULL DEFAULT '{}',
  payload_mode TEXT NOT NULL DEFAULT 'thin',
  event_schema_version TEXT NOT NULL DEFAULT 'v1',
  status TEXT NOT NULL DEFAULT 'active',
  disabled_reason TEXT,
  active_from_seq BIGINT NOT NULL,
  active_until_seq BIGINT,
  expires_at TIMESTAMPTZ,
  current_secret_id TEXT,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_webhook_subscription_scope ON cur_webhook_subscription (scope);
