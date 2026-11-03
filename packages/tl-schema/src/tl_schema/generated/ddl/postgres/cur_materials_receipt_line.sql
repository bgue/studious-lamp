CREATE TABLE IF NOT EXISTS cur_materials_receipt_line (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  receipt_id TEXT COLLATE "C" NOT NULL,
  line_no BIGINT NOT NULL,
  project_item_id TEXT COLLATE "C" NOT NULL,
  qty NUMERIC NOT NULL,
  uom TEXT COLLATE "C" NOT NULL,
  heat_no TEXT COLLATE "C",
  condition TEXT COLLATE "C" NOT NULL,
  serials_text TEXT COLLATE "C",
  lot_id TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_materials_receipt_line_receipt_line ON cur_materials_receipt_line (receipt_id, line_no);

CREATE INDEX IF NOT EXISTS ix_cur_materials_receipt_line_item ON cur_materials_receipt_line (project_item_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_receipt_line_lot ON cur_materials_receipt_line (lot_id);
