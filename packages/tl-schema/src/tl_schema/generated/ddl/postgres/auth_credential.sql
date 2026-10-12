CREATE TABLE IF NOT EXISTS auth_credential (
  account_id TEXT COLLATE "C" PRIMARY KEY,
  password_hash TEXT COLLATE "C" NOT NULL,
  updated_at TEXT COLLATE "C" NOT NULL
);
