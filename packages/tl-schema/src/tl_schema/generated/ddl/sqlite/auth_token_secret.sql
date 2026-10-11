CREATE TABLE IF NOT EXISTS auth_token_secret (
  token_hash TEXT PRIMARY KEY,
  token_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_auth_token_secret_token_id ON auth_token_secret (token_id);
