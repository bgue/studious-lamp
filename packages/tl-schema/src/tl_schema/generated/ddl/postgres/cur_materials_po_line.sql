CREATE TABLE IF NOT EXISTS cur_materials_po_line (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  po_number TEXT COLLATE "C" NOT NULL,
  line_no BIGINT NOT NULL,
  project_item_id TEXT COLLATE "C" NOT NULL,
  qty_ordered NUMERIC NOT NULL,
  uom TEXT COLLATE "C" NOT NULL,
  promised_date TEXT COLLATE "C",
  supplier_text TEXT COLLATE "C" NOT NULL,
  qty_received NUMERIC NOT NULL DEFAULT 0,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_po_line_po ON cur_materials_po_line (scope, po_number, line_no);
