CREATE TABLE IF NOT EXISTS cur_correspondence_commercial_item (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  contract_clause_id TEXT,
  aware_on TEXT,
  derived_from_id TEXT,
  currency TEXT,
  estimated_value TEXT,
  estimated_hours TEXT,
  cost_code_impacts_json TEXT NOT NULL DEFAULT '{}',
  schedule_impact_days INTEGER,
  schedule_impact_note TEXT,
  entitlement_basis TEXT,
  assessed_value TEXT,
  assessed_on TEXT,
  assessment_status TEXT,
  assessment_note TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_commercial_item_scope_clause ON cur_correspondence_commercial_item (scope, contract_clause_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_commercial_item_scope_status ON cur_correspondence_commercial_item (scope, assessment_status);
