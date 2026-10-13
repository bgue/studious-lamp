CREATE TABLE IF NOT EXISTS cur_documents_transmittal_item (
  item_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  transmittal_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  revision_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  document_number TEXT NOT NULL,
  revision_code TEXT NOT NULL,
  issue_status TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_documents_transmittal_item_transmittal_revision ON cur_documents_transmittal_item (transmittal_id, revision_id);

CREATE INDEX IF NOT EXISTS ix_cur_documents_transmittal_item_revision ON cur_documents_transmittal_item (revision_id);

CREATE INDEX IF NOT EXISTS ix_cur_documents_transmittal_item_transmittal_position ON cur_documents_transmittal_item (transmittal_id, position);
