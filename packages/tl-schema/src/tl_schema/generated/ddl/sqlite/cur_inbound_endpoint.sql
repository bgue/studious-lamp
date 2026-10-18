CREATE TABLE IF NOT EXISTS cur_inbound_endpoint (
  endpoint_id TEXT PRIMARY KEY,
  app TEXT NOT NULL,
  name TEXT NOT NULL,
  scope TEXT NOT NULL,
  version INTEGER NOT NULL,
  auth TEXT NOT NULL DEFAULT 'hmac_sha256',
  mapping TEXT NOT NULL,
  mapping_language TEXT NOT NULL DEFAULT 'jsonata-restricted@1',
  external_schema TEXT,
  allowed_commands_json TEXT NOT NULL DEFAULT '{}',
  service_actor TEXT NOT NULL,
  access TEXT NOT NULL DEFAULT 'user',
  max_body_bytes INTEGER NOT NULL,
  rate_per_minute INTEGER NOT NULL,
  dry_run INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 0,
  current_secret_id TEXT,
  owner TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  stream_version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_inbound_endpoint_inbound_endpoint_path ON cur_inbound_endpoint (app, name);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_inbound_endpoint_inbound_endpoint_service_actor ON cur_inbound_endpoint (service_actor);

CREATE INDEX IF NOT EXISTS ix_cur_inbound_endpoint_scope ON cur_inbound_endpoint (scope);
