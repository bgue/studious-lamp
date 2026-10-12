CREATE TABLE IF NOT EXISTS cur_engineering_tag_class (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  label TEXT NOT NULL,
  family TEXT NOT NULL,
  required_psets_json TEXT NOT NULL DEFAULT '{}',
  itr_templates_json TEXT NOT NULL DEFAULT '{}',
  mnemonics_json TEXT NOT NULL DEFAULT '{}',
  lifecycle TEXT NOT NULL DEFAULT 'active',
  superseded_by TEXT,
  edition TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_engineering_tag_class_scope_code ON cur_engineering_tag_class (scope, code);
