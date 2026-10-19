CREATE TABLE IF NOT EXISTS cur_cost_snapshot_value (
  row_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  cost_code_id TEXT NOT NULL,
  code TEXT NOT NULL,
  period TEXT NOT NULL,
  revision INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  hours_budget REAL,
  hours_actual REAL,
  hours_earned REAL,
  hours_ftc REAL,
  hours_eac REAL,
  quantity_budget REAL,
  quantity_actual REAL,
  quantity_earned REAL,
  quantity_ftc REAL,
  quantity_eac REAL,
  amount_budget REAL,
  amount_actual REAL,
  amount_earned REAL,
  amount_ftc REAL,
  amount_eac REAL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_cost_snapshot_value_code_as_of ON cur_cost_snapshot_value (cost_code_id, as_of);

CREATE INDEX IF NOT EXISTS ix_cur_cost_snapshot_value_snapshot ON cur_cost_snapshot_value (snapshot_id, code);
