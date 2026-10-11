CREATE TABLE IF NOT EXISTS auth_credential (
  account_id TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
