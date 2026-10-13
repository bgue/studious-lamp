CREATE TABLE IF NOT EXISTS cur_documents_reviewer (
  reviewer_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  review_cycle_id TEXT COLLATE "C" NOT NULL,
  revision_id TEXT COLLATE "C" NOT NULL,
  document_id TEXT COLLATE "C" NOT NULL,
  reviewer TEXT COLLATE "C" NOT NULL,
  due_date TEXT COLLATE "C",
  outcome TEXT COLLATE "C",
  comment TEXT COLLATE "C",
  responded_on TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_documents_reviewer_cycle_reviewer ON cur_documents_reviewer (review_cycle_id, reviewer);

CREATE INDEX IF NOT EXISTS ix_cur_documents_reviewer_cycle ON cur_documents_reviewer (review_cycle_id);

CREATE INDEX IF NOT EXISTS ix_cur_documents_reviewer_scope_reviewer ON cur_documents_reviewer (scope, reviewer, outcome);
