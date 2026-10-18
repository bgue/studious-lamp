CREATE TABLE IF NOT EXISTS cur_action_definition (
  definition_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  label TEXT NOT NULL,
  description TEXT,
  scope TEXT NOT NULL,
  version INTEGER NOT NULL,
  applies_to_json TEXT NOT NULL DEFAULT '{}',
  parameters_json TEXT NOT NULL DEFAULT '{}',
  executor TEXT NOT NULL,
  executor_config_json TEXT NOT NULL DEFAULT '{}',
  side_effect_class TEXT NOT NULL,
  requires_approval INTEGER NOT NULL DEFAULT 0,
  access TEXT NOT NULL DEFAULT 'user',
  result_handling_json TEXT NOT NULL DEFAULT '{}',
  owner TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  retired INTEGER NOT NULL DEFAULT 0,
  integration_app TEXT,
  secret_id TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  stream_version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_action_definition_action_definition_name ON cur_action_definition (name);

CREATE INDEX IF NOT EXISTS ix_cur_action_definition_scope ON cur_action_definition (scope);
