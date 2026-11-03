CREATE TABLE IF NOT EXISTS cur_materials_item_master (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  category TEXT NOT NULL,
  base_uom TEXT NOT NULL,
  size_text TEXT,
  rating_text TEXT,
  material_code TEXT,
  consumable INTEGER NOT NULL DEFAULT 0,
  retired INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_item_master_code ON cur_materials_item_master (scope, code);
