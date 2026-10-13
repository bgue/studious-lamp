CREATE TABLE IF NOT EXISTS cur_documents_review_cycle (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  revision_id TEXT COLLATE "C" NOT NULL,
  document_id TEXT COLLATE "C" NOT NULL,
  round BIGINT NOT NULL,
  state TEXT COLLATE "C" NOT NULL DEFAULT 'open',
  due_date TEXT COLLATE "C",
  outcome TEXT COLLATE "C",
  opened_on TEXT COLLATE "C",
  closed_on TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_review_cycle_revision_round ON cur_documents_review_cycle (revision_id, round);

CREATE INDEX IF NOT EXISTS ix_cur_documents_review_cycle_scope_state_due ON cur_documents_review_cycle (scope, state, due_date);
