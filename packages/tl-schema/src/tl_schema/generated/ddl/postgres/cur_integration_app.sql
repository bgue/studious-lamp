CREATE TABLE IF NOT EXISTS cur_integration_app (
  app_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  label TEXT COLLATE "C" NOT NULL,
  description TEXT COLLATE "C",
  owner TEXT COLLATE "C" NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_by TEXT COLLATE "C" NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_integration_app_integration_app_name ON cur_integration_app (name);

CREATE INDEX IF NOT EXISTS ix_cur_integration_app_scope ON cur_integration_app (scope);
