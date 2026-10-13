CREATE TABLE IF NOT EXISTS cur_documents_transmittal_item (
  item_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  transmittal_id TEXT COLLATE "C" NOT NULL,
  position BIGINT NOT NULL,
  revision_id TEXT COLLATE "C" NOT NULL,
  document_id TEXT COLLATE "C" NOT NULL,
  document_number TEXT COLLATE "C" NOT NULL,
  revision_code TEXT COLLATE "C" NOT NULL,
  issue_status TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_documents_transmittal_item_transmittal_revision ON cur_documents_transmittal_item (transmittal_id, revision_id);

CREATE INDEX IF NOT EXISTS ix_cur_documents_transmittal_item_revision ON cur_documents_transmittal_item (revision_id);

CREATE INDEX IF NOT EXISTS ix_cur_documents_transmittal_item_transmittal_position ON cur_documents_transmittal_item (transmittal_id, position);
