CREATE TABLE IF NOT EXISTS cur_correspondence_commercial_item (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  contract_clause_id TEXT COLLATE "C",
  aware_on TEXT COLLATE "C",
  derived_from_id TEXT COLLATE "C",
  currency TEXT COLLATE "C",
  estimated_value TEXT COLLATE "C",
  estimated_hours TEXT COLLATE "C",
  cost_code_impacts_json JSONB NOT NULL DEFAULT '{}',
  schedule_impact_days BIGINT,
  schedule_impact_note TEXT COLLATE "C",
  entitlement_basis TEXT COLLATE "C",
  assessed_value TEXT COLLATE "C",
  assessed_on TEXT COLLATE "C",
  assessment_status TEXT COLLATE "C",
  assessment_note TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_commercial_item_scope_clause ON cur_correspondence_commercial_item (scope, contract_clause_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_commercial_item_scope_status ON cur_correspondence_commercial_item (scope, assessment_status);
