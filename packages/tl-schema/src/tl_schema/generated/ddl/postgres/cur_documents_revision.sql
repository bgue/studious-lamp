CREATE TABLE IF NOT EXISTS cur_documents_revision (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  document_id TEXT COLLATE "C" NOT NULL,
  document_number TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  ordinal BIGINT NOT NULL,
  previous_revision_id TEXT COLLATE "C",
  purpose TEXT COLLATE "C",
  change_note TEXT COLLATE "C",
  revision_date TEXT COLLATE "C",
  intended_status TEXT COLLATE "C",
  issue_status TEXT COLLATE "C",
  status_class TEXT COLLATE "C",
  issued_on TEXT COLLATE "C",
  is_current BOOLEAN NOT NULL DEFAULT FALSE,
  superseded_by TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_documents_revision_document_code ON cur_documents_revision (document_id, code);

CREATE INDEX IF NOT EXISTS ix_cur_documents_revision_document_current ON cur_documents_revision (document_id, is_current);

CREATE INDEX IF NOT EXISTS ix_cur_documents_revision_document_ordinal ON cur_documents_revision (document_id, ordinal);

CREATE INDEX IF NOT EXISTS ix_cur_documents_revision_scope_issue_status ON cur_documents_revision (scope, issue_status);
