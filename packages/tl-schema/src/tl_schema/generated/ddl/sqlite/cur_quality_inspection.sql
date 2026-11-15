CREATE TABLE IF NOT EXISTS cur_quality_inspection (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  subject_id TEXT,
  for_iwp_id TEXT,
  checklist_id TEXT,
  checklist_version INTEGER,
  point TEXT,
  area TEXT,
  planned_on TEXT,
  scheduled_for TEXT,
  inspector TEXT,
  result TEXT,
  done_at TEXT,
  answers_json TEXT NOT NULL DEFAULT '[]',
  note TEXT,
  recorded_by TEXT,
  verified_by TEXT,
  verified_on TEXT,
  reinspection_of_id TEXT,
  cancel_reason TEXT,
  punch_count INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_area ON cur_quality_inspection (area);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_checklist ON cur_quality_inspection (checklist_id);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_for_iwp ON cur_quality_inspection (for_iwp_id);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_reinspection_of ON cur_quality_inspection (reinspection_of_id);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_scheduled_for ON cur_quality_inspection (scheduled_for);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_subject ON cur_quality_inspection (subject_id);
