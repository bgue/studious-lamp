CREATE TABLE IF NOT EXISTS cur_materials_mto_line (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  mto_id TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  project_item_id TEXT NOT NULL,
  qty NUMERIC NOT NULL,
  uom TEXT NOT NULL,
  tag_id TEXT,
  work_package_id TEXT,
  reserved_qty NUMERIC NOT NULL DEFAULT 0,
  issued_qty NUMERIC NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_materials_mto_line_mto_line ON cur_materials_mto_line (mto_id, line_no);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_line_item ON cur_materials_mto_line (project_item_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_line_mto ON cur_materials_mto_line (mto_id, line_no);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_line_work_package ON cur_materials_mto_line (work_package_id);
