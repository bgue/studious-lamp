CREATE TABLE IF NOT EXISTS cur_setting (
  change_id TEXT COLLATE "C" PRIMARY KEY,
  key TEXT COLLATE "C" NOT NULL,
  layer TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  value_json JSONB NOT NULL DEFAULT '{}',
  reset BOOLEAN NOT NULL DEFAULT FALSE,
  old_value_json JSONB NOT NULL DEFAULT '{}',
  old_set BOOLEAN NOT NULL DEFAULT FALSE,
  reason TEXT COLLATE "C",
  actor TEXT COLLATE "C" NOT NULL,
  source TEXT COLLATE "C" NOT NULL,
  accept_risk BOOLEAN NOT NULL DEFAULT FALSE,
  applies_at TIMESTAMPTZ,
  effective_us BIGINT NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL,
  seq BIGINT NOT NULL,
  version BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_setting_key ON cur_setting (key);

CREATE INDEX IF NOT EXISTS ix_cur_setting_layer ON cur_setting (layer);

CREATE INDEX IF NOT EXISTS ix_cur_setting_seq ON cur_setting (seq);
