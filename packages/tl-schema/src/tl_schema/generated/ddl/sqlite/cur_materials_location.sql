CREATE TABLE IF NOT EXISTS cur_materials_location (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  kind TEXT NOT NULL,
  parent_id TEXT,
  depth INTEGER NOT NULL DEFAULT 0,
  retired INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_location_parent ON cur_materials_location (parent_id);
