CREATE TABLE IF NOT EXISTS cur_forms_intake_item (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code_id TEXT COLLATE "C",
  template_id TEXT COLLATE "C",
  template_version BIGINT,
  template_hash TEXT COLLATE "C",
  body_mac TEXT COLLATE "C",
  body_bytes BIGINT,
  received_at TIMESTAMPTZ,
  accepted_as TEXT COLLATE "C",
  accepted_by TEXT COLLATE "C",
  accepted_on TEXT COLLATE "C",
  on_behalf_of_claim_json JSONB,
  rejected_reason TEXT COLLATE "C",
  rejected_by TEXT COLLATE "C",
  purged_at TIMESTAMPTZ,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_forms_intake_item_code ON cur_forms_intake_item (code_id);

CREATE INDEX IF NOT EXISTS ix_cur_forms_intake_item_received ON cur_forms_intake_item (received_at);
