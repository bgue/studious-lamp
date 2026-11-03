CREATE TABLE IF NOT EXISTS cur_materials_lot (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  project_item_id TEXT COLLATE "C" NOT NULL,
  heat_no TEXT COLLATE "C",
  receipt_id TEXT COLLATE "C" NOT NULL,
  receipt_line BIGINT NOT NULL,
  uom TEXT COLLATE "C" NOT NULL,
  issued_net NUMERIC NOT NULL DEFAULT 0,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_materials_lot_receipt_line ON cur_materials_lot (receipt_id, receipt_line);

CREATE INDEX IF NOT EXISTS ix_cur_materials_lot_item ON cur_materials_lot (project_item_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_lot_receipt ON cur_materials_lot (receipt_id, receipt_line);
