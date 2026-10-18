CREATE TABLE IF NOT EXISTS cur_inbound_endpoint (
  endpoint_id TEXT COLLATE "C" PRIMARY KEY,
  app TEXT COLLATE "C" NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  version BIGINT NOT NULL,
  auth TEXT COLLATE "C" NOT NULL DEFAULT 'hmac_sha256',
  mapping TEXT COLLATE "C" NOT NULL,
  mapping_language TEXT COLLATE "C" NOT NULL DEFAULT 'jsonata-restricted@1',
  external_schema TEXT COLLATE "C",
  allowed_commands_json JSONB NOT NULL DEFAULT '{}',
  service_actor TEXT COLLATE "C" NOT NULL,
  access TEXT COLLATE "C" NOT NULL DEFAULT 'user',
  max_body_bytes BIGINT NOT NULL,
  rate_per_minute BIGINT NOT NULL,
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  current_secret_id TEXT COLLATE "C",
  owner TEXT COLLATE "C" NOT NULL,
  created_by TEXT COLLATE "C" NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  stream_version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_inbound_endpoint_inbound_endpoint_path ON cur_inbound_endpoint (app, name);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_inbound_endpoint_inbound_endpoint_service_actor ON cur_inbound_endpoint (service_actor);

CREATE INDEX IF NOT EXISTS ix_cur_inbound_endpoint_scope ON cur_inbound_endpoint (scope);
