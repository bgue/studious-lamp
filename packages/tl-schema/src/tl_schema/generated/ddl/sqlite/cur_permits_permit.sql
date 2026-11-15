CREATE TABLE IF NOT EXISTS cur_permits_permit (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  permit_type TEXT NOT NULL,
  for_record_id TEXT,
  area TEXT,
  location_text TEXT,
  holder TEXT,
  requested_by TEXT,
  needed_from TEXT,
  needed_until TEXT,
  approved_by TEXT,
  issued_by TEXT,
  issued_at TEXT,
  valid_until TEXT,
  precautions_json TEXT NOT NULL DEFAULT '[]',
  revalidation_count INTEGER NOT NULL DEFAULT 0,
  last_revalidated_at TEXT,
  suspend_reason TEXT,
  handback_note TEXT,
  closed_by TEXT,
  reject_reason TEXT,
  cancel_reason TEXT,
  lapse_flagged_for TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_permits_permit_area ON cur_permits_permit (area);

CREATE INDEX IF NOT EXISTS ix_cur_permits_permit_for_record ON cur_permits_permit (for_record_id);

CREATE INDEX IF NOT EXISTS ix_cur_permits_permit_permit_type ON cur_permits_permit (permit_type);

CREATE INDEX IF NOT EXISTS ix_cur_permits_permit_valid_until ON cur_permits_permit (valid_until);
