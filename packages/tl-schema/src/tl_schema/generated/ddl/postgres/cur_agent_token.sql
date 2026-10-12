CREATE TABLE IF NOT EXISTS cur_agent_token (
  token_id TEXT COLLATE "C" PRIMARY KEY,
  account_id TEXT COLLATE "C" NOT NULL,
  label TEXT COLLATE "C" NOT NULL,
  expires_at TEXT COLLATE "C",
  revoked BIGINT NOT NULL DEFAULT 0,
  revoked_at TEXT COLLATE "C",
  revoke_reason TEXT COLLATE "C",
  issued_by TEXT COLLATE "C" NOT NULL,
  issued_at TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_agent_token_account_id ON cur_agent_token (account_id);
