CREATE TABLE IF NOT EXISTS cur_rule (
  rule_id TEXT PRIMARY KEY,
  key TEXT NOT NULL,
  title TEXT NOT NULL,
  scope TEXT NOT NULL,
  version INTEGER NOT NULL,
  when_json TEXT NOT NULL DEFAULT '{}',
  condition TEXT,
  then_json TEXT NOT NULL DEFAULT '{}',
  mode TEXT NOT NULL DEFAULT 'propose',
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

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_rule_rule_key ON cur_rule (key);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_rule_rule_service_actor ON cur_rule (service_actor);

CREATE INDEX IF NOT EXISTS ix_cur_rule_scope ON cur_rule (scope);
