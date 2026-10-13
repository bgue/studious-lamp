CREATE TABLE IF NOT EXISTS cur_documents_rendition (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  revision_id TEXT COLLATE "C" NOT NULL,
  document_id TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  file_id TEXT COLLATE "C" NOT NULL,
  filename TEXT COLLATE "C" NOT NULL,
  content_type TEXT COLLATE "C" NOT NULL,
  size BIGINT NOT NULL,
  sha256 TEXT COLLATE "C" NOT NULL,
  page_count BIGINT,
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  superseded_by TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_rendition_document_kind ON cur_documents_rendition (document_id, kind);

CREATE INDEX IF NOT EXISTS ix_cur_documents_rendition_revision_kind ON cur_documents_rendition (revision_id, kind, is_current);
