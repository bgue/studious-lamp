CREATE TABLE IF NOT EXISTS cur_materials_project_item (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  item_master_id TEXT NOT NULL,
  category TEXT NOT NULL,
  uom TEXT NOT NULL,
  consumable INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_project_item_item_master ON cur_materials_project_item (item_master_id);
