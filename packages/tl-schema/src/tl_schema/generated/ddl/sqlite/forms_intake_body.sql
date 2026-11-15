CREATE TABLE IF NOT EXISTS forms_intake_body (
  item_id TEXT NOT NULL,
  code_id TEXT NOT NULL,
  salt TEXT NOT NULL,
  body TEXT NOT NULL,
  received_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_forms_intake_body_item_id ON forms_intake_body (item_id);

CREATE INDEX IF NOT EXISTS ix_forms_intake_body_code ON forms_intake_body (code_id);

CREATE INDEX IF NOT EXISTS ix_forms_intake_body_received ON forms_intake_body (received_at);
