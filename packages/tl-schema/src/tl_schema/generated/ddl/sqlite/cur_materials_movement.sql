CREATE TABLE IF NOT EXISTS cur_materials_movement (
  seq INTEGER PRIMARY KEY,
  scope TEXT NOT NULL,
  lot_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  qty NUMERIC NOT NULL,
  uom TEXT NOT NULL,
  direction TEXT,
  from_location_id TEXT,
  to_location_id TEXT,
  cost_code_id TEXT,
  mto_line_id TEXT,
  iwp_id TEXT,
  requisition_id TEXT,
  person TEXT,
  reason TEXT,
  actor TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  correlation_id TEXT
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_movement_cost_code ON cur_materials_movement (cost_code_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_movement_lot ON cur_materials_movement (lot_id, seq);

CREATE INDEX IF NOT EXISTS ix_cur_materials_movement_mto_line ON cur_materials_movement (mto_line_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_movement_scope_recorded ON cur_materials_movement (scope, recorded_at);
