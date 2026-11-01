CREATE TABLE IF NOT EXISTS cur_materials_mto (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  derived_document_id TEXT NOT NULL,
  revision_id TEXT NOT NULL,
  line_count INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_document ON cur_materials_mto (derived_document_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_revision ON cur_materials_mto (revision_id);
