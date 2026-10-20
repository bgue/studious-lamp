CREATE TABLE IF NOT EXISTS cur_inbound_endpoint_version (
  version_id TEXT PRIMARY KEY,
  endpoint_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  definition_json TEXT NOT NULL DEFAULT '{}',
  seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_inbound_endpoint_version_inbound_endpoint_version_pair ON cur_inbound_endpoint_version (endpoint_id, version);

CREATE INDEX IF NOT EXISTS ix_cur_inbound_endpoint_version_endpoint_id ON cur_inbound_endpoint_version (endpoint_id);
