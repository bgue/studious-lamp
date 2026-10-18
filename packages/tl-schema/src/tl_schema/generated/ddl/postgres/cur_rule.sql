CREATE TABLE IF NOT EXISTS cur_rule (
  rule_id TEXT COLLATE "C" PRIMARY KEY,
  key TEXT COLLATE "C" NOT NULL,
  title TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  version BIGINT NOT NULL,
  when_json JSONB NOT NULL DEFAULT '{}',
  condition TEXT COLLATE "C",
  then_json JSONB NOT NULL DEFAULT '{}',
  mode TEXT COLLATE "C" NOT NULL DEFAULT 'propose',
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

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_rule_rule_key ON cur_rule (key);

CREATE INDEX IF NOT EXISTS ix_cur_rule_scope ON cur_rule (scope);
