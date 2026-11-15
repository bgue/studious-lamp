CREATE TABLE IF NOT EXISTS cur_forms_submission (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  template_id TEXT COLLATE "C",
  template_version BIGINT,
  template_hash TEXT COLLATE "C",
  subject_id TEXT COLLATE "C",
  answers_json JSONB NOT NULL DEFAULT '[]',
  answer_class TEXT COLLATE "C",
  draft_saves BIGINT NOT NULL DEFAULT 0,
  author TEXT COLLATE "C",
  submitted_on TEXT COLLATE "C",
  reviewed_by TEXT COLLATE "C",
  reviewed_on TEXT COLLATE "C",
  review_note TEXT COLLATE "C",
  void_reason TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_forms_submission_subject ON cur_forms_submission (subject_id);

CREATE INDEX IF NOT EXISTS ix_cur_forms_submission_template ON cur_forms_submission (template_id);
