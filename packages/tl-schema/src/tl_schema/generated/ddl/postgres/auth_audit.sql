CREATE TABLE IF NOT EXISTS auth_audit (
  audit_id TEXT COLLATE "C" PRIMARY KEY,
  at TEXT COLLATE "C" NOT NULL,
  event TEXT COLLATE "C" NOT NULL,
  username_key TEXT COLLATE "C",
  account_id TEXT COLLATE "C",
  actor TEXT COLLATE "C",
  detail TEXT COLLATE "C"
);

CREATE INDEX IF NOT EXISTS ix_auth_audit_at ON auth_audit (at);

CREATE INDEX IF NOT EXISTS ix_auth_audit_event ON auth_audit (event);
