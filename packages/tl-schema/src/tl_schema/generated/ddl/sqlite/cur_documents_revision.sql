CREATE TABLE IF NOT EXISTS cur_documents_revision (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  document_id TEXT NOT NULL,
  document_number TEXT NOT NULL,
  code TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  previous_revision_id TEXT,
  purpose TEXT,
  change_note TEXT,
  revision_date TEXT,
  intended_status TEXT,
  issue_status TEXT,
  status_class TEXT,
  issued_on TEXT,
  is_current INTEGER NOT NULL DEFAULT 0,
  superseded_by TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_documents_revision_document_code ON cur_documents_revision (document_id, code);

CREATE INDEX IF NOT EXISTS ix_cur_documents_revision_document_current ON cur_documents_revision (document_id, is_current);

CREATE INDEX IF NOT EXISTS ix_cur_documents_revision_document_ordinal ON cur_documents_revision (document_id, ordinal);

CREATE INDEX IF NOT EXISTS ix_cur_documents_revision_scope_issue_status ON cur_documents_revision (scope, issue_status);
