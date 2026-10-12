CREATE TABLE IF NOT EXISTS cur_agent_token (
  token_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  label TEXT NOT NULL,
  expires_at TEXT,
  revoked INTEGER NOT NULL DEFAULT 0,
  revoked_at TEXT,
  revoke_reason TEXT,
  issued_by TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_agent_token_account_id ON cur_agent_token (account_id);
