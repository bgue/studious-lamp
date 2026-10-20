CREATE TABLE IF NOT EXISTS cur_correspondence_clearance (
  clearance_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  record_id TEXT NOT NULL,
  account TEXT NOT NULL,
  granted_by TEXT NOT NULL,
  granted_on TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_correspondence_clearance_record_account ON cur_correspondence_clearance (record_id, account);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_clearance_account ON cur_correspondence_clearance (account);
