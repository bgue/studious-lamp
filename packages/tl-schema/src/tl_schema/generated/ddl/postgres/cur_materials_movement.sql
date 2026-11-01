CREATE TABLE IF NOT EXISTS cur_materials_movement (
  seq BIGINT PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  lot_id TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  qty NUMERIC NOT NULL,
  uom TEXT COLLATE "C" NOT NULL,
  direction TEXT COLLATE "C",
  from_location_id TEXT COLLATE "C",
  to_location_id TEXT COLLATE "C",
  cost_code_id TEXT COLLATE "C",
  mto_line_id TEXT COLLATE "C",
  iwp_id TEXT COLLATE "C",
  requisition_id TEXT COLLATE "C",
  person TEXT COLLATE "C",
  reason TEXT COLLATE "C",
  actor TEXT COLLATE "C" NOT NULL,
  recorded_at TEXT COLLATE "C" NOT NULL,
  correlation_id TEXT COLLATE "C"
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_movement_cost_code ON cur_materials_movement (cost_code_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_movement_lot ON cur_materials_movement (lot_id, seq);

CREATE INDEX IF NOT EXISTS ix_cur_materials_movement_mto_line ON cur_materials_movement (mto_line_id);

CREATE INDEX IF NOT EXISTS ix_cur_materials_movement_scope_recorded ON cur_materials_movement (scope, recorded_at);
