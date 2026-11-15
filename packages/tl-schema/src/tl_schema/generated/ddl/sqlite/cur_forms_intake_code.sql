CREATE TABLE IF NOT EXISTS cur_forms_intake_code (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  template_id TEXT,
  template_version INTEGER,
  template_hash TEXT,
  context_id TEXT,
  context_type TEXT,
  heading TEXT,
  controller_role TEXT,
  issued_by TEXT,
  issued_at TEXT,
  expires_on TEXT NOT NULL,
  revoked_at TEXT,
  revoked_by TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_forms_intake_code_code_hash ON cur_forms_intake_code (code_hash);

CREATE INDEX IF NOT EXISTS ix_cur_forms_intake_code_context ON cur_forms_intake_code (context_id);
