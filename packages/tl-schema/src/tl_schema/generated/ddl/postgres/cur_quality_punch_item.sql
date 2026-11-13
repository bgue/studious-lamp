CREATE TABLE IF NOT EXISTS cur_quality_punch_item (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  area TEXT COLLATE "C",
  system TEXT COLLATE "C",
  due_on TEXT COLLATE "C",
  category TEXT COLLATE "C" NOT NULL DEFAULT 'B',
  assignee TEXT COLLATE "C",
  raised_by TEXT COLLATE "C" NOT NULL,
  source_id TEXT COLLATE "C",
  cleared_by TEXT COLLATE "C",
  cleared_on TEXT COLLATE "C",
  clear_note TEXT COLLATE "C",
  verified_by TEXT COLLATE "C",
  verified_on TEXT COLLATE "C",
  reopen_count BIGINT NOT NULL DEFAULT 0,
  last_reopen_reason TEXT COLLATE "C",
  void_reason TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_quality_punch_item_area ON cur_quality_punch_item (area);

CREATE INDEX IF NOT EXISTS ix_cur_quality_punch_item_due_on ON cur_quality_punch_item (due_on);

CREATE INDEX IF NOT EXISTS ix_cur_quality_punch_item_source ON cur_quality_punch_item (source_id);

CREATE INDEX IF NOT EXISTS ix_cur_quality_punch_item_system ON cur_quality_punch_item (system);
