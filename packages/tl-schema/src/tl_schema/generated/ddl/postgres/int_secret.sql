CREATE TABLE IF NOT EXISTS int_secret (
  secret_id TEXT COLLATE "C" PRIMARY KEY,
  owner_kind TEXT COLLATE "C" NOT NULL,
  owner_id TEXT COLLATE "C" NOT NULL,
  secret TEXT COLLATE "C" NOT NULL,
  state TEXT COLLATE "C" NOT NULL DEFAULT 'active',
  created_at TEXT COLLATE "C" NOT NULL,
  expires_at TEXT COLLATE "C"
);

CREATE INDEX IF NOT EXISTS ix_int_secret_owner ON int_secret (owner_kind, owner_id, state);
