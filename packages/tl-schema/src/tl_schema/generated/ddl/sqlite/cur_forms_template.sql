CREATE TABLE IF NOT EXISTS cur_forms_template (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  template_version INTEGER NOT NULL DEFAULT 1,
  format_version INTEGER NOT NULL DEFAULT 1,
  form_fields_json TEXT NOT NULL DEFAULT '[]',
  field_count INTEGER,
  content_hash TEXT,
  supersedes_id TEXT,
  bound_record_type TEXT,
  answer_class TEXT,
  intake TEXT,
  purpose TEXT,
  accepts_as_json TEXT,
  published_on TEXT,
  retired_on TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_forms_template_content_hash ON cur_forms_template (content_hash);

CREATE INDEX IF NOT EXISTS ix_cur_forms_template_supersedes ON cur_forms_template (supersedes_id);
