CREATE TABLE IF NOT EXISTS cur_quality_punch_item (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  area TEXT,
  system TEXT,
  due_on TEXT,
  category TEXT NOT NULL DEFAULT 'B',
  assignee TEXT,
  raised_by TEXT NOT NULL,
  source_id TEXT,
  cleared_by TEXT,
  cleared_on TEXT,
  clear_note TEXT,
  verified_by TEXT,
  verified_on TEXT,
  reopen_count INTEGER NOT NULL DEFAULT 0,
  last_reopen_reason TEXT,
  void_reason TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_quality_punch_item_area ON cur_quality_punch_item (area);

CREATE INDEX IF NOT EXISTS ix_cur_quality_punch_item_due_on ON cur_quality_punch_item (due_on);

CREATE INDEX IF NOT EXISTS ix_cur_quality_punch_item_source ON cur_quality_punch_item (source_id);

CREATE INDEX IF NOT EXISTS ix_cur_quality_punch_item_system ON cur_quality_punch_item (system);
