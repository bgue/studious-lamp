CREATE TABLE IF NOT EXISTS cur_enricher (
  enricher_id TEXT COLLATE "C" PRIMARY KEY,
  name TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  version BIGINT NOT NULL,
  code_version TEXT COLLATE "C" NOT NULL,
  model_ref TEXT COLLATE "C",
  when_json JSONB NOT NULL DEFAULT '{}',
  properties_json JSONB NOT NULL DEFAULT '{}',
  service_actor TEXT COLLATE "C" NOT NULL,
  access TEXT COLLATE "C" NOT NULL DEFAULT 'user',
  owner TEXT COLLATE "C" NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  enabled_from_seq BIGINT NOT NULL DEFAULT 0,
  integration_app TEXT COLLATE "C",
  created_by TEXT COLLATE "C" NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  stream_version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_enricher_enricher_name ON cur_enricher (name);

CREATE INDEX IF NOT EXISTS ix_cur_enricher_scope ON cur_enricher (scope);
