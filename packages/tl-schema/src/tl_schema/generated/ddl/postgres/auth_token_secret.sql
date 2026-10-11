CREATE TABLE IF NOT EXISTS auth_token_secret (
  token_hash TEXT COLLATE "C" PRIMARY KEY,
  token_id TEXT COLLATE "C" NOT NULL,
  created_at TEXT COLLATE "C" NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_auth_token_secret_token_id ON auth_token_secret (token_id);
