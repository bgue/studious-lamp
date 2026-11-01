CREATE TABLE IF NOT EXISTS cur_materials_project_item (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  item_master_id TEXT COLLATE "C" NOT NULL,
  category TEXT COLLATE "C" NOT NULL,
  uom TEXT COLLATE "C" NOT NULL,
  consumable BOOLEAN NOT NULL DEFAULT FALSE,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_project_item_item_master ON cur_materials_project_item (item_master_id);
