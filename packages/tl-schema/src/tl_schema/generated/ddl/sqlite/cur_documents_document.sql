CREATE TABLE IF NOT EXISTS cur_documents_document (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  number TEXT NOT NULL,
  doc_type TEXT,
  discipline TEXT,
  originator TEXT,
  confidentiality TEXT,
  revision_scheme TEXT NOT NULL,
  pattern_code TEXT,
  current_revision_id TEXT,
  current_revision_code TEXT,
  current_revision_status TEXT,
  current_revision_class TEXT,
  current_revision_issued_on TEXT,
  superseded_by TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_document_scope_current_status ON cur_documents_document (scope, current_revision_status);

CREATE INDEX IF NOT EXISTS ix_cur_documents_document_scope_discipline ON cur_documents_document (scope, discipline);

CREATE INDEX IF NOT EXISTS ix_cur_documents_document_scope_type ON cur_documents_document (scope, doc_type);
