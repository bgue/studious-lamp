CREATE TABLE IF NOT EXISTS cur_engineering_tag_class (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  label TEXT COLLATE "C" NOT NULL,
  family TEXT COLLATE "C" NOT NULL,
  required_psets_json JSONB NOT NULL DEFAULT '{}',
  itr_templates_json JSONB NOT NULL DEFAULT '{}',
  mnemonics_json JSONB NOT NULL DEFAULT '{}',
  lifecycle TEXT COLLATE "C" NOT NULL DEFAULT 'active',
  superseded_by TEXT COLLATE "C",
  edition TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_engineering_tag_class_scope_code ON cur_engineering_tag_class (scope, code);
