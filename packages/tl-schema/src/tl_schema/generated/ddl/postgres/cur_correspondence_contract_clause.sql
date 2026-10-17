CREATE TABLE IF NOT EXISTS cur_correspondence_contract_clause (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  contract TEXT COLLATE "C" NOT NULL,
  clause_number TEXT COLLATE "C" NOT NULL,
  time_bar_days BIGINT,
  time_bar_day_type TEXT COLLATE "C",
  notice_requirements TEXT COLLATE "C",
  required_recipients_json JSONB NOT NULL DEFAULT '{}',
  service_method TEXT COLLATE "C",
  contract_document_id TEXT COLLATE "C",
  domains_json JSONB NOT NULL DEFAULT '{}',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_contract_clause_scope_contract ON cur_correspondence_contract_clause (scope, contract);
