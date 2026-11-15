CREATE TABLE IF NOT EXISTS cur_forms_intake_code (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code_hash TEXT COLLATE "C" NOT NULL,
  template_id TEXT COLLATE "C",
  template_version BIGINT,
  template_hash TEXT COLLATE "C",
  context_id TEXT COLLATE "C",
  context_type TEXT COLLATE "C",
  heading TEXT COLLATE "C",
  controller_role TEXT COLLATE "C",
  issued_by TEXT COLLATE "C",
  issued_at TIMESTAMPTZ,
  expires_on DATE NOT NULL,
  revoked_at TIMESTAMPTZ,
  revoked_by TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_forms_intake_code_code_hash ON cur_forms_intake_code (code_hash);

CREATE INDEX IF NOT EXISTS ix_cur_forms_intake_code_context ON cur_forms_intake_code (context_id);
