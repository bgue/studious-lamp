CREATE TABLE IF NOT EXISTS cur_cost_costcode (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  parent_code TEXT COLLATE "C",
  level BIGINT NOT NULL DEFAULT 1,
  uom TEXT COLLATE "C",
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  snapshot_id TEXT COLLATE "C",
  period TEXT COLLATE "C",
  as_of TEXT COLLATE "C",
  hours_budget DOUBLE PRECISION,
  hours_actual DOUBLE PRECISION,
  hours_earned DOUBLE PRECISION,
  hours_ftc DOUBLE PRECISION,
  hours_eac DOUBLE PRECISION,
  quantity_budget DOUBLE PRECISION,
  quantity_actual DOUBLE PRECISION,
  quantity_earned DOUBLE PRECISION,
  quantity_ftc DOUBLE PRECISION,
  quantity_eac DOUBLE PRECISION,
  amount_budget DOUBLE PRECISION,
  amount_actual DOUBLE PRECISION,
  amount_earned DOUBLE PRECISION,
  amount_ftc DOUBLE PRECISION,
  amount_eac DOUBLE PRECISION,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_cost_costcode_scope_code ON cur_cost_costcode (scope, code);

CREATE INDEX IF NOT EXISTS ix_cur_cost_costcode_scope_parent ON cur_cost_costcode (scope, parent_code);
