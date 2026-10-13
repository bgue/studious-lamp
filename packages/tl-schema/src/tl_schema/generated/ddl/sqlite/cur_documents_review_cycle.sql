CREATE TABLE IF NOT EXISTS cur_documents_review_cycle (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  revision_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  round INTEGER NOT NULL,
  state TEXT NOT NULL DEFAULT 'open',
  due_date TEXT,
  outcome TEXT,
  opened_on TEXT,
  closed_on TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_review_cycle_revision_round ON cur_documents_review_cycle (revision_id, round);

CREATE INDEX IF NOT EXISTS ix_cur_documents_review_cycle_scope_state_due ON cur_documents_review_cycle (scope, state, due_date);
