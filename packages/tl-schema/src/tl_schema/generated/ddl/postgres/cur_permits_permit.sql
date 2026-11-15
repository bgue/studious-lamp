CREATE TABLE IF NOT EXISTS cur_permits_permit (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  permit_type TEXT COLLATE "C" NOT NULL,
  for_record_id TEXT COLLATE "C",
  area TEXT COLLATE "C",
  location_text TEXT COLLATE "C",
  holder TEXT COLLATE "C",
  requested_by TEXT COLLATE "C",
  needed_from TEXT COLLATE "C",
  needed_until TEXT COLLATE "C",
  approved_by TEXT COLLATE "C",
  issued_by TEXT COLLATE "C",
  issued_at TIMESTAMPTZ,
  valid_until TIMESTAMPTZ,
  precautions_json JSONB NOT NULL DEFAULT '[]',
  revalidation_count BIGINT NOT NULL DEFAULT 0,
  last_revalidated_at TIMESTAMPTZ,
  suspend_reason TEXT COLLATE "C",
  handback_note TEXT COLLATE "C",
  closed_by TEXT COLLATE "C",
  reject_reason TEXT COLLATE "C",
  cancel_reason TEXT COLLATE "C",
  lapse_flagged_for TIMESTAMPTZ,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_permits_permit_area ON cur_permits_permit (area);

CREATE INDEX IF NOT EXISTS ix_cur_permits_permit_for_record ON cur_permits_permit (for_record_id);

CREATE INDEX IF NOT EXISTS ix_cur_permits_permit_permit_type ON cur_permits_permit (permit_type);

CREATE INDEX IF NOT EXISTS ix_cur_permits_permit_valid_until ON cur_permits_permit (valid_until);
