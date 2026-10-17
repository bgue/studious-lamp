CREATE TABLE IF NOT EXISTS cur_cost_costcode (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  parent_code TEXT,
  level INTEGER NOT NULL DEFAULT 1,
  uom TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  snapshot_id TEXT,
  period TEXT,
  as_of TEXT,
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

CREATE INDEX IF NOT EXISTS ix_cur_cost_costcode_scope_code ON cur_cost_costcode (scope, code);

CREATE INDEX IF NOT EXISTS ix_cur_cost_costcode_scope_parent ON cur_cost_costcode (scope, parent_code);
