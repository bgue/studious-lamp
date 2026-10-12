CREATE TABLE IF NOT EXISTS auth_session (
  token_hash TEXT COLLATE "C" PRIMARY KEY,
  account_id TEXT COLLATE "C" NOT NULL,
  created_at TEXT COLLATE "C" NOT NULL,
  expires_at TEXT COLLATE "C" NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_auth_session_account_id ON auth_session (account_id);
