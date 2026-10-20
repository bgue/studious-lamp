CREATE TABLE IF NOT EXISTS cur_correspondence_clearance (
  clearance_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  record_id TEXT COLLATE "C" NOT NULL,
  account TEXT COLLATE "C" NOT NULL,
  granted_by TEXT COLLATE "C" NOT NULL,
  granted_on TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_correspondence_clearance_record_account ON cur_correspondence_clearance (record_id, account);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_clearance_account ON cur_correspondence_clearance (account);
