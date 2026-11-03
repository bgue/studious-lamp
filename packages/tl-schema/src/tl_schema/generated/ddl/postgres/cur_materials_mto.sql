CREATE TABLE IF NOT EXISTS cur_materials_mto (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  derived_document_id TEXT COLLATE "C" NOT NULL,
  revision_id TEXT COLLATE "C" NOT NULL,
  line_count BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_document ON cur_materials_mto (derived_document_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_revision ON cur_materials_mto (revision_id);
