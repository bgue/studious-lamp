CREATE TABLE IF NOT EXISTS cur_scaffold_scaffold (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  request_id TEXT COLLATE "C" NOT NULL,
  for_record_id TEXT COLLATE "C",
  location_text TEXT COLLATE "C",
  elevation TEXT COLLATE "C",
  gridline TEXT COLLATE "C",
  load_class TEXT COLLATE "C",
  tag TEXT COLLATE "C",
  tagged_on TEXT COLLATE "C",
  last_inspected_on TEXT COLLATE "C",
  next_due_on TEXT COLLATE "C",
  flagged_due_on TEXT COLLATE "C",
  inspection_count BIGINT NOT NULL DEFAULT 0,
  modify_reason TEXT COLLATE "C",
  dismantle_reason TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_scaffold_scaffold_for_record ON cur_scaffold_scaffold (for_record_id);

CREATE INDEX IF NOT EXISTS ix_cur_scaffold_scaffold_request ON cur_scaffold_scaffold (request_id);
