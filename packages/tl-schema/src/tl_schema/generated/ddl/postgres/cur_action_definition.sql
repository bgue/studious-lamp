CREATE TABLE IF NOT EXISTS cur_action_definition (
  definition_id TEXT COLLATE "C" PRIMARY KEY,
  name TEXT COLLATE "C" NOT NULL,
  label TEXT COLLATE "C" NOT NULL,
  description TEXT COLLATE "C",
  scope TEXT COLLATE "C" NOT NULL,
  version BIGINT NOT NULL,
  applies_to_json JSONB NOT NULL DEFAULT '{}',
  parameters_json JSONB NOT NULL DEFAULT '{}',
  executor TEXT COLLATE "C" NOT NULL,
  executor_config_json JSONB NOT NULL DEFAULT '{}',
  side_effect_class TEXT COLLATE "C" NOT NULL,
  requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
  access TEXT COLLATE "C" NOT NULL DEFAULT 'user',
  result_handling_json JSONB NOT NULL DEFAULT '{}',
  owner TEXT COLLATE "C" NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  retired BOOLEAN NOT NULL DEFAULT FALSE,
  integration_app TEXT COLLATE "C",
  secret_id TEXT COLLATE "C",
  created_by TEXT COLLATE "C" NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  stream_version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_action_definition_action_definition_name ON cur_action_definition (name);

CREATE INDEX IF NOT EXISTS ix_cur_action_definition_scope ON cur_action_definition (scope);
