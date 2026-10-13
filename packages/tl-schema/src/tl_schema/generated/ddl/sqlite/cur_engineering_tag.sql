CREATE TABLE IF NOT EXISTS cur_engineering_tag (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  number TEXT NOT NULL,
  class_code TEXT,
  area TEXT,
  mnemonic TEXT,
  sequence INTEGER,
  segments_json TEXT NOT NULL DEFAULT '{}',
  pattern_code TEXT,
  number_status TEXT NOT NULL DEFAULT 'ok',
  violations_json TEXT NOT NULL DEFAULT '{}',
  origin TEXT NOT NULL DEFAULT 'created',
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_tag_scope_class ON cur_engineering_tag (scope, class_code);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_tag_scope_mnemonic_area ON cur_engineering_tag (scope, mnemonic, area);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_tag_scope_number_status ON cur_engineering_tag (scope, number_status);
