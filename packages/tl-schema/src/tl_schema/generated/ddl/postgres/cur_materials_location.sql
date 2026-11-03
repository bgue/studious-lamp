CREATE TABLE IF NOT EXISTS cur_materials_location (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  parent_id TEXT COLLATE "C",
  depth BIGINT NOT NULL DEFAULT 0,
  retired BOOLEAN NOT NULL DEFAULT FALSE,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_materials_location_parent ON cur_materials_location (parent_id);
