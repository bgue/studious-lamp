CREATE TABLE IF NOT EXISTS cur_correspondence_contract_clause (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  contract TEXT NOT NULL,
  clause_number TEXT NOT NULL,
  time_bar_days INTEGER,
  time_bar_day_type TEXT,
  notice_requirements TEXT,
  required_recipients_json_json TEXT NOT NULL DEFAULT '{}',
  service_method TEXT,
  contract_document_id TEXT,
  domains_json_json TEXT NOT NULL DEFAULT '{}',
  is_active INTEGER NOT NULL DEFAULT 1,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_contract_clause_scope_contract ON cur_correspondence_contract_clause (scope, contract);
