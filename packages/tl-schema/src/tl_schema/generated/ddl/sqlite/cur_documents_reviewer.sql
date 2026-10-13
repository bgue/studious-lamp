CREATE TABLE IF NOT EXISTS cur_documents_reviewer (
  reviewer_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  review_cycle_id TEXT NOT NULL,
  revision_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  due_date TEXT,
  outcome TEXT,
  comment TEXT,
  responded_on TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_documents_reviewer_cycle_reviewer ON cur_documents_reviewer (review_cycle_id, reviewer);

CREATE INDEX IF NOT EXISTS ix_cur_documents_reviewer_cycle ON cur_documents_reviewer (review_cycle_id);

CREATE INDEX IF NOT EXISTS ix_cur_documents_reviewer_scope_reviewer ON cur_documents_reviewer (scope, reviewer, outcome);
