CREATE TABLE IF NOT EXISTS cur_setting (
  change_id TEXT PRIMARY KEY,
  key TEXT NOT NULL,
  layer TEXT NOT NULL,
  scope TEXT NOT NULL,
  value_json TEXT NOT NULL DEFAULT '{}',
  reset INTEGER NOT NULL DEFAULT 0,
  old_value_json TEXT NOT NULL DEFAULT '{}',
  old_set INTEGER NOT NULL DEFAULT 0,
  reason TEXT,
  actor TEXT NOT NULL,
  source TEXT NOT NULL,
  accept_risk INTEGER NOT NULL DEFAULT 0,
  applies_at TEXT,
  effective_us INTEGER NOT NULL,
  recorded_at TEXT NOT NULL,
  seq INTEGER NOT NULL,
  version INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_setting_key ON cur_setting (key);

CREATE INDEX IF NOT EXISTS ix_cur_setting_layer ON cur_setting (layer);

CREATE INDEX IF NOT EXISTS ix_cur_setting_seq ON cur_setting (seq);
