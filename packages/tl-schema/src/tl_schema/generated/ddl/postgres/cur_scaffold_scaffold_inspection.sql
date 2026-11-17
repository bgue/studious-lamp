CREATE TABLE IF NOT EXISTS cur_scaffold_scaffold_inspection (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  scaffold_id TEXT COLLATE "C" NOT NULL,
  inspector TEXT COLLATE "C" NOT NULL,
  inspected_on TEXT COLLATE "C" NOT NULL,
  result TEXT COLLATE "C" NOT NULL,
  tag TEXT COLLATE "C" NOT NULL,
  note TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_scaffold_scaffold_inspection_scaffold ON cur_scaffold_scaffold_inspection (scaffold_id);
