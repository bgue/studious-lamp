CREATE TABLE IF NOT EXISTS cur_materials_receipt (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  po_line_id TEXT COLLATE "C",
  supplier_text TEXT COLLATE "C" NOT NULL,
  delivery_ref TEXT COLLATE "C",
  received_on TEXT COLLATE "C" NOT NULL,
  location_id TEXT COLLATE "C" NOT NULL,
  inspected_by TEXT COLLATE "C",
  inspected_on TEXT COLLATE "C",
  decided_by TEXT COLLATE "C",
  decided_on TEXT COLLATE "C",
  rejection_reason TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_receipt_location ON cur_materials_receipt (location_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_receipt_po_line ON cur_materials_receipt (po_line_id);
