CREATE TABLE IF NOT EXISTS cur_documents_derived_document (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  source_document_id TEXT COLLATE "C" NOT NULL,
  source_revision_id TEXT COLLATE "C" NOT NULL,
  source_document_number TEXT COLLATE "C" NOT NULL,
  source_revision_code TEXT COLLATE "C" NOT NULL,
  source_ref TEXT COLLATE "C" NOT NULL,
  schema_id TEXT COLLATE "C" NOT NULL,
  schema_code TEXT COLLATE "C" NOT NULL,
  schema_version TEXT COLLATE "C" NOT NULL,
  method TEXT COLLATE "C" NOT NULL DEFAULT 'manual',
  previous_derived_id TEXT COLLATE "C",
  content_rev BIGINT NOT NULL DEFAULT 0,
  published_rev BIGINT,
  validation_status TEXT COLLATE "C" NOT NULL DEFAULT 'none',
  row_count BIGINT,
  error_count BIGINT,
  published_correlation_id TEXT COLLATE "C",
  published_at TEXT COLLATE "C",
  published_count BIGINT,
  last_job_id TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_derived_document_scope_revision ON cur_documents_derived_document (scope, source_revision_id);

CREATE INDEX IF NOT EXISTS ix_cur_documents_derived_document_scope_schema ON cur_documents_derived_document (scope, schema_code);

CREATE INDEX IF NOT EXISTS ix_cur_documents_derived_document_source_document ON cur_documents_derived_document (source_document_id, schema_code);
