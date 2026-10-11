CREATE TABLE IF NOT EXISTS auth_audit (
  audit_id TEXT PRIMARY KEY,
  at TEXT NOT NULL,
  event TEXT NOT NULL,
  username_key TEXT,
  account_id TEXT,
  actor TEXT,
  detail TEXT,
  count INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_auth_audit_at ON auth_audit (at);

CREATE INDEX IF NOT EXISTS ix_auth_audit_event ON auth_audit (event);
