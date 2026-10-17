CREATE TABLE IF NOT EXISTS cur_documents_document_schema (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  semver TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  target_kind TEXT,
  key_column TEXT,
  json_schema_json TEXT NOT NULL DEFAULT '{}',
  sample_json TEXT,
  mapping_json TEXT,
  mapping_notes TEXT,
  doc_types_json TEXT NOT NULL DEFAULT '{}',
  content_hash TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  retired_reason TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_document_schema_scope_code ON cur_documents_document_schema (scope, code, ordinal);
