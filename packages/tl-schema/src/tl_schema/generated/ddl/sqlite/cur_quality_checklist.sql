CREATE TABLE IF NOT EXISTS cur_quality_checklist (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  discipline TEXT,
  checklist_version INTEGER NOT NULL DEFAULT 1,
  questions_json TEXT NOT NULL DEFAULT '[]',
  question_count INTEGER,
  supersedes_id TEXT,
  published_by TEXT,
  published_on TEXT,
  retired_on TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_quality_checklist_discipline ON cur_quality_checklist (discipline);

CREATE INDEX IF NOT EXISTS ix_cur_quality_checklist_supersedes ON cur_quality_checklist (supersedes_id);
