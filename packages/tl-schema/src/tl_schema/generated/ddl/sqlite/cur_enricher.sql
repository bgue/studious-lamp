CREATE TABLE IF NOT EXISTS cur_enricher (
  enricher_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  scope TEXT NOT NULL,
  version INTEGER NOT NULL,
  code_version TEXT NOT NULL,
  model_ref TEXT,
  when_json TEXT NOT NULL DEFAULT '{}',
  properties_json TEXT NOT NULL DEFAULT '{}',
  service_actor TEXT NOT NULL,
  access TEXT NOT NULL DEFAULT 'user',
  owner TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  enabled_from_seq INTEGER NOT NULL DEFAULT 0,
  integration_app TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  stream_version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_enricher_enricher_name ON cur_enricher (name);

CREATE INDEX IF NOT EXISTS ix_cur_enricher_scope ON cur_enricher (scope);
