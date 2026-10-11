CREATE TABLE IF NOT EXISTS cur_account (
  account_id TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  display_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  roles_json TEXT NOT NULL DEFAULT '{}',
  is_admin INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_account_username ON cur_account (username);

CREATE INDEX IF NOT EXISTS ix_cur_account_is_admin ON cur_account (is_admin);
