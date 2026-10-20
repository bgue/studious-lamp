CREATE TABLE IF NOT EXISTS cur_correspondence_technical_item (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  question TEXT COLLATE "C" NOT NULL,
  proposed_solution TEXT COLLATE "C",
  discipline TEXT COLLATE "C",
  required_by TEXT COLLATE "C",
  potential_cost_impact TEXT COLLATE "C" NOT NULL DEFAULT 'unknown',
  potential_schedule_impact TEXT COLLATE "C" NOT NULL DEFAULT 'unknown',
  answer TEXT COLLATE "C",
  answered_on TEXT COLLATE "C",
  answer_cost_impact TEXT COLLATE "C",
  answer_schedule_impact TEXT COLLATE "C",
  answer_item_id TEXT COLLATE "C",
  answering_revision_id TEXT COLLATE "C",
  review_decision TEXT COLLATE "C",
  reviewed_on TEXT COLLATE "C",
  review_note TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_technical_item_scope_discipline ON cur_correspondence_technical_item (scope, discipline);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_technical_item_scope_required_by ON cur_correspondence_technical_item (scope, required_by);
