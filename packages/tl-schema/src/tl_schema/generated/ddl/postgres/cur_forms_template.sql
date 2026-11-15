CREATE TABLE IF NOT EXISTS cur_forms_template (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  template_version BIGINT NOT NULL DEFAULT 1,
  format_version BIGINT NOT NULL DEFAULT 1,
  form_fields_json JSONB NOT NULL DEFAULT '[]',
  field_count BIGINT,
  content_hash TEXT COLLATE "C",
  supersedes_id TEXT COLLATE "C",
  bound_record_type TEXT COLLATE "C",
  answer_class TEXT COLLATE "C",
  intake TEXT COLLATE "C",
  purpose TEXT COLLATE "C",
  accepts_as_json JSONB,
  published_on TEXT COLLATE "C",
  retired_on TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_forms_template_content_hash ON cur_forms_template (content_hash);

CREATE INDEX IF NOT EXISTS ix_cur_forms_template_supersedes ON cur_forms_template (supersedes_id);
