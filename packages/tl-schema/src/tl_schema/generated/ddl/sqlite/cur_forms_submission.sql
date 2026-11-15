CREATE TABLE IF NOT EXISTS cur_forms_submission (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  template_id TEXT,
  template_version INTEGER,
  template_hash TEXT,
  subject_id TEXT,
  answers_json TEXT NOT NULL DEFAULT '[]',
  answer_class TEXT,
  draft_saves INTEGER NOT NULL DEFAULT 0,
  author TEXT,
  submitted_on TEXT,
  reviewed_by TEXT,
  reviewed_on TEXT,
  review_note TEXT,
  void_reason TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_forms_submission_subject ON cur_forms_submission (subject_id);

CREATE INDEX IF NOT EXISTS ix_cur_forms_submission_template ON cur_forms_submission (template_id);
