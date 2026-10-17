CREATE TABLE IF NOT EXISTS cur_documents_document_schema (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  semver TEXT COLLATE "C" NOT NULL,
  ordinal BIGINT NOT NULL,
  target_kind TEXT COLLATE "C",
  key_column TEXT COLLATE "C",
  json_schema_json JSONB NOT NULL DEFAULT '{}',
  sample_json JSONB,
  mapping_json JSONB,
  mapping_notes TEXT COLLATE "C",
  doc_types_json JSONB NOT NULL DEFAULT '{}',
  content_hash TEXT COLLATE "C" NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  retired_reason TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_document_schema_scope_code ON cur_documents_document_schema (scope, code, ordinal);
