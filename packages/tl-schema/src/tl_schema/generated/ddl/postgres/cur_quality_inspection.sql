CREATE TABLE IF NOT EXISTS cur_quality_inspection (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  subject_id TEXT COLLATE "C",
  for_iwp_id TEXT COLLATE "C",
  checklist_id TEXT COLLATE "C",
  checklist_version BIGINT,
  point TEXT COLLATE "C",
  area TEXT COLLATE "C",
  planned_on TEXT COLLATE "C",
  scheduled_for TEXT COLLATE "C",
  inspector TEXT COLLATE "C",
  result TEXT COLLATE "C",
  done_at TIMESTAMPTZ,
  answers_json JSONB NOT NULL DEFAULT '[]',
  note TEXT COLLATE "C",
  recorded_by TEXT COLLATE "C",
  verified_by TEXT COLLATE "C",
  verified_on TEXT COLLATE "C",
  reinspection_of_id TEXT COLLATE "C",
  cancel_reason TEXT COLLATE "C",
  punch_count BIGINT NOT NULL DEFAULT 0,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_area ON cur_quality_inspection (area);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_checklist ON cur_quality_inspection (checklist_id);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_for_iwp ON cur_quality_inspection (for_iwp_id);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_reinspection_of ON cur_quality_inspection (reinspection_of_id);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_scheduled_for ON cur_quality_inspection (scheduled_for);

CREATE INDEX IF NOT EXISTS ix_cur_quality_inspection_subject ON cur_quality_inspection (subject_id);
