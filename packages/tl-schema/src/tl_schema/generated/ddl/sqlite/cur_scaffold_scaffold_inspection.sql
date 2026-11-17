CREATE TABLE IF NOT EXISTS cur_scaffold_scaffold_inspection (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  scaffold_id TEXT NOT NULL,
  inspector TEXT NOT NULL,
  inspected_on TEXT NOT NULL,
  result TEXT NOT NULL,
  tag TEXT NOT NULL,
  note TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_scaffold_scaffold_inspection_scaffold ON cur_scaffold_scaffold_inspection (scaffold_id);
