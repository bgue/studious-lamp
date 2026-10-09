CREATE TABLE IF NOT EXISTS cur_links (
  link_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  from_id TEXT NOT NULL,
  to_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  pin TEXT,
  note TEXT,
  source TEXT NOT NULL,
  confidence REAL,
  reason TEXT,
  declined INTEGER NOT NULL DEFAULT 0,
  verified_by TEXT,
  verified_at TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_links_scope ON cur_links (scope);

CREATE INDEX IF NOT EXISTS ix_cur_links_from_id ON cur_links (from_id);

CREATE INDEX IF NOT EXISTS ix_cur_links_to_id ON cur_links (to_id);
