CREATE TABLE IF NOT EXISTS cur_materials_po_line (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  po_number TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  project_item_id TEXT NOT NULL,
  qty_ordered NUMERIC NOT NULL,
  uom TEXT NOT NULL,
  promised_date TEXT,
  supplier_text TEXT NOT NULL,
  qty_received NUMERIC NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_po_line_po ON cur_materials_po_line (scope, po_number, line_no);
