CREATE TABLE IF NOT EXISTS cur_documents_document (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  number TEXT COLLATE "C" NOT NULL,
  doc_type TEXT COLLATE "C",
  discipline TEXT COLLATE "C",
  originator TEXT COLLATE "C",
  confidentiality TEXT COLLATE "C",
  revision_scheme TEXT COLLATE "C" NOT NULL,
  pattern_code TEXT COLLATE "C",
  current_revision_id TEXT COLLATE "C",
  current_revision_code TEXT COLLATE "C",
  current_revision_status TEXT COLLATE "C",
  current_revision_class TEXT COLLATE "C",
  current_revision_issued_on TEXT COLLATE "C",
  superseded_by TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_document_scope_current_status ON cur_documents_document (scope, current_revision_status);

CREATE INDEX IF NOT EXISTS ix_cur_documents_document_scope_discipline ON cur_documents_document (scope, discipline);

CREATE INDEX IF NOT EXISTS ix_cur_documents_document_scope_type ON cur_documents_document (scope, doc_type);
