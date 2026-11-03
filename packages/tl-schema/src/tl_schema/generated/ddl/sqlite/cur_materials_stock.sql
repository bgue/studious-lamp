CREATE TABLE IF NOT EXISTS cur_materials_stock (
  scope TEXT NOT NULL,
  lot_id TEXT NOT NULL,
  location_id TEXT NOT NULL,
  on_hand NUMERIC NOT NULL,
  reserved NUMERIC NOT NULL,
  available NUMERIC NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_materials_stock_lot_location ON cur_materials_stock (lot_id, location_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_stock_location ON cur_materials_stock (location_id);
