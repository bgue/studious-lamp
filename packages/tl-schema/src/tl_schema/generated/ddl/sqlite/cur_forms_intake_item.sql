CREATE TABLE IF NOT EXISTS cur_forms_intake_item (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code_id TEXT,
  template_id TEXT,
  template_version INTEGER,
  template_hash TEXT,
  body_mac TEXT,
  body_bytes INTEGER,
  received_at TEXT,
  accepted_as TEXT,
  accepted_by TEXT,
  accepted_on TEXT,
  on_behalf_of_claim_json TEXT,
  rejected_reason TEXT,
  rejected_by TEXT,
  purged_at TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_forms_intake_item_code ON cur_forms_intake_item (code_id);

CREATE INDEX IF NOT EXISTS ix_cur_forms_intake_item_received ON cur_forms_intake_item (received_at);
