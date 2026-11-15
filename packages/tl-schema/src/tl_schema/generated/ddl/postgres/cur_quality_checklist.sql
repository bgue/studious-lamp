CREATE TABLE IF NOT EXISTS cur_quality_checklist (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  discipline TEXT COLLATE "C",
  checklist_version BIGINT NOT NULL DEFAULT 1,
  questions_json JSONB NOT NULL DEFAULT '[]',
  question_count BIGINT,
  supersedes_id TEXT COLLATE "C",
  published_by TEXT COLLATE "C",
  published_on TEXT COLLATE "C",
  retired_on TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_quality_checklist_discipline ON cur_quality_checklist (discipline);

CREATE INDEX IF NOT EXISTS ix_cur_quality_checklist_supersedes ON cur_quality_checklist (supersedes_id);
