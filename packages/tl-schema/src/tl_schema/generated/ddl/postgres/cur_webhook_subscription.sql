CREATE TABLE IF NOT EXISTS cur_webhook_subscription (
  subscription_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  owner TEXT COLLATE "C" NOT NULL,
  integration_app TEXT COLLATE "C",
  target_url TEXT COLLATE "C" NOT NULL,
  filter_json JSONB NOT NULL DEFAULT '{}',
  payload_mode TEXT COLLATE "C" NOT NULL DEFAULT 'thin',
  event_schema_version TEXT COLLATE "C" NOT NULL DEFAULT 'v1',
  status TEXT COLLATE "C" NOT NULL DEFAULT 'active',
  disabled_reason TEXT COLLATE "C",
  active_windows_json JSONB NOT NULL DEFAULT '{}',
  expires_at TIMESTAMPTZ,
  current_secret_id TEXT COLLATE "C",
  created_by TEXT COLLATE "C" NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_webhook_subscription_scope ON cur_webhook_subscription (scope);
