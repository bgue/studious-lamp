CREATE TABLE IF NOT EXISTS cur_documents_rendition (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  revision_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  file_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  page_count INTEGER,
  is_current INTEGER NOT NULL DEFAULT 1,
  superseded_by TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_rendition_document_kind ON cur_documents_rendition (document_id, kind);

CREATE INDEX IF NOT EXISTS ix_cur_documents_rendition_revision_kind ON cur_documents_rendition (revision_id, kind, is_current);
