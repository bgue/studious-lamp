CREATE TABLE IF NOT EXISTS cur_correspondence_technical_item (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  question TEXT NOT NULL,
  proposed_solution TEXT,
  discipline TEXT,
  required_by TEXT,
  potential_cost_impact TEXT NOT NULL DEFAULT 'unknown',
  potential_schedule_impact TEXT NOT NULL DEFAULT 'unknown',
  answer TEXT,
  answered_on TEXT,
  answer_cost_impact TEXT,
  answer_schedule_impact TEXT,
  answer_item_id TEXT,
  answering_revision_id TEXT,
  review_decision TEXT,
  reviewed_on TEXT,
  review_note TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_technical_item_scope_discipline ON cur_correspondence_technical_item (scope, discipline);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_technical_item_scope_required_by ON cur_correspondence_technical_item (scope, required_by);
