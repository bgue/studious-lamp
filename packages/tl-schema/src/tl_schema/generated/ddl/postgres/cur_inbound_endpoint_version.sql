CREATE TABLE IF NOT EXISTS cur_inbound_endpoint_version (
  version_id TEXT COLLATE "C" PRIMARY KEY,
  endpoint_id TEXT COLLATE "C" NOT NULL,
  version BIGINT NOT NULL,
  definition_json JSONB NOT NULL DEFAULT '{}',
  seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_inbound_endpoint_version_inbound_endpoint_version_pair ON cur_inbound_endpoint_version (endpoint_id, version);

CREATE INDEX IF NOT EXISTS ix_cur_inbound_endpoint_version_endpoint_id ON cur_inbound_endpoint_version (endpoint_id);
