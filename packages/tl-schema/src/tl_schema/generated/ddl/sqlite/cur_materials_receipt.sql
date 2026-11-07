CREATE TABLE IF NOT EXISTS cur_materials_receipt (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  po_line_id TEXT,
  supplier_text TEXT NOT NULL,
  delivery_ref TEXT,
  received_on TEXT NOT NULL,
  location_id TEXT NOT NULL,
  inspected_by TEXT,
  inspected_on TEXT,
  decided_by TEXT,
  decided_on TEXT,
  rejection_reason TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_receipt_location ON cur_materials_receipt (location_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_receipt_po_line ON cur_materials_receipt (po_line_id);
