CREATE TABLE IF NOT EXISTS cur_materials_mto_line (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  mto_id TEXT COLLATE "C" NOT NULL,
  line_no BIGINT NOT NULL,
  project_item_id TEXT COLLATE "C" NOT NULL,
  qty NUMERIC NOT NULL,
  uom TEXT COLLATE "C" NOT NULL,
  tag_id TEXT COLLATE "C",
  work_package_id TEXT COLLATE "C",
  reserved_qty NUMERIC NOT NULL DEFAULT 0,
  issued_qty NUMERIC NOT NULL DEFAULT 0,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_materials_mto_line_mto_line ON cur_materials_mto_line (mto_id, line_no);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_line_item ON cur_materials_mto_line (project_item_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_line_mto ON cur_materials_mto_line (mto_id, line_no);

CREATE INDEX IF NOT EXISTS ix_cur_materials_mto_line_work_package ON cur_materials_mto_line (work_package_id);
