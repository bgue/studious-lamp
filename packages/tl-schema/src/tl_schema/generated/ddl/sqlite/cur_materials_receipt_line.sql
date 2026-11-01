CREATE TABLE IF NOT EXISTS cur_materials_receipt_line (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  receipt_id TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  project_item_id TEXT NOT NULL,
  qty NUMERIC NOT NULL,
  uom TEXT NOT NULL,
  heat_no TEXT,
  condition TEXT NOT NULL,
  serials_text TEXT,
  lot_id TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_materials_receipt_line_receipt_line ON cur_materials_receipt_line (receipt_id, line_no);

CREATE INDEX IF NOT EXISTS ix_cur_materials_receipt_line_item ON cur_materials_receipt_line (project_item_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_receipt_line_lot ON cur_materials_receipt_line (lot_id);
