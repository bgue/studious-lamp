CREATE TABLE IF NOT EXISTS cur_materials_item_master (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  category TEXT COLLATE "C" NOT NULL,
  base_uom TEXT COLLATE "C" NOT NULL,
  size_text TEXT COLLATE "C",
  rating_text TEXT COLLATE "C",
  material_code TEXT COLLATE "C",
  consumable BOOLEAN NOT NULL DEFAULT FALSE,
  retired BOOLEAN NOT NULL DEFAULT FALSE,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_item_master_code ON cur_materials_item_master (scope, code);
