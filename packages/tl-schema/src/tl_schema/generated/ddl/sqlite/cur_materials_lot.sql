CREATE TABLE IF NOT EXISTS cur_materials_lot (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  project_item_id TEXT NOT NULL,
  heat_no TEXT,
  receipt_id TEXT NOT NULL,
  receipt_line INTEGER NOT NULL,
  uom TEXT NOT NULL,
  issued_net NUMERIC NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_materials_lot_receipt_line ON cur_materials_lot (receipt_id, receipt_line);

CREATE INDEX IF NOT EXISTS ix_cur_materials_lot_item ON cur_materials_lot (project_item_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_lot_receipt ON cur_materials_lot (receipt_id, receipt_line);
