CREATE TABLE IF NOT EXISTS int_secret (
  secret_id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  secret TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  expires_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_int_secret_owner ON int_secret (owner_kind, owner_id, state);
