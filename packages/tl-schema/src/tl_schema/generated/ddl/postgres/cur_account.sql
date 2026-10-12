CREATE TABLE IF NOT EXISTS cur_account (
  account_id TEXT COLLATE "C" PRIMARY KEY,
  username TEXT COLLATE "C" NOT NULL,
  display_name TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  roles_json JSONB NOT NULL DEFAULT '{}',
  is_admin BIGINT NOT NULL DEFAULT 0,
  status TEXT COLLATE "C" NOT NULL DEFAULT 'active',
  created_by TEXT COLLATE "C" NOT NULL,
  created_at TEXT COLLATE "C" NOT NULL,
  updated_at TEXT COLLATE "C" NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_account_username ON cur_account (username);

CREATE INDEX IF NOT EXISTS ix_cur_account_is_admin ON cur_account (is_admin);
