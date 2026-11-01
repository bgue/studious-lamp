CREATE TABLE IF NOT EXISTS cur_materials_reservation (
  scope TEXT NOT NULL,
  lot_id TEXT NOT NULL,
  location_id TEXT NOT NULL,
  mto_line_id TEXT NOT NULL,
  qty NUMERIC NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_materials_reservation_lot_location_line ON cur_materials_reservation (lot_id, location_id, mto_line_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_reservation_mto_line ON cur_materials_reservation (mto_line_id);
