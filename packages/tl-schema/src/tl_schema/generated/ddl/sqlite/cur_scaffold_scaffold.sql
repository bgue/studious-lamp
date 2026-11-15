CREATE TABLE IF NOT EXISTS cur_scaffold_scaffold (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  request_id TEXT NOT NULL,
  for_record_id TEXT,
  location_text TEXT,
  elevation TEXT,
  gridline TEXT,
  load_class TEXT,
  tag TEXT,
  tagged_on TEXT,
  last_inspected_on TEXT,
  next_due_on TEXT,
  flagged_due_on TEXT,
  inspection_count INTEGER NOT NULL DEFAULT 0,
  modify_reason TEXT,
  dismantle_reason TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_scaffold_scaffold_for_record ON cur_scaffold_scaffold (for_record_id);

CREATE INDEX IF NOT EXISTS ix_cur_scaffold_scaffold_request ON cur_scaffold_scaffold (request_id);
