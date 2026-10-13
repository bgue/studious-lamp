CREATE TABLE IF NOT EXISTS cur_engineering_tag (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  number TEXT COLLATE "C" NOT NULL,
  class_code TEXT COLLATE "C",
  area TEXT COLLATE "C",
  mnemonic TEXT COLLATE "C",
  sequence BIGINT,
  segments_json JSONB NOT NULL DEFAULT '{}',
  pattern_code TEXT COLLATE "C",
  number_status TEXT COLLATE "C" NOT NULL DEFAULT 'ok',
  violations_json JSONB NOT NULL DEFAULT '{}',
  origin TEXT COLLATE "C" NOT NULL DEFAULT 'created',
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_tag_scope_class ON cur_engineering_tag (scope, class_code);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_tag_scope_mnemonic_area ON cur_engineering_tag (scope, mnemonic, area);

CREATE INDEX IF NOT EXISTS ix_cur_engineering_tag_scope_number_status ON cur_engineering_tag (scope, number_status);
