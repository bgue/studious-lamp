CREATE TABLE IF NOT EXISTS cur_documents_derived_document (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  source_document_id TEXT NOT NULL,
  source_revision_id TEXT NOT NULL,
  source_document_number TEXT NOT NULL,
  source_revision_code TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  schema_id TEXT NOT NULL,
  schema_code TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  method TEXT NOT NULL DEFAULT 'manual',
  previous_derived_id TEXT,
  content_rev INTEGER NOT NULL DEFAULT 0,
  published_rev INTEGER,
  validation_status TEXT NOT NULL DEFAULT 'none',
  row_count INTEGER,
  error_count INTEGER,
  published_correlation_id TEXT,
  published_at TEXT,
  published_count INTEGER,
  last_job_id TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_derived_document_scope_revision ON cur_documents_derived_document (scope, source_revision_id);

CREATE INDEX IF NOT EXISTS ix_cur_documents_derived_document_scope_schema ON cur_documents_derived_document (scope, schema_code);

CREATE INDEX IF NOT EXISTS ix_cur_documents_derived_document_source_document ON cur_documents_derived_document (source_document_id, schema_code);
