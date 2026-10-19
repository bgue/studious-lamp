CREATE TABLE IF NOT EXISTS cur_cost_snapshot_value (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  snapshot_id TEXT COLLATE "C" NOT NULL,
  cost_code_id TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  period TEXT COLLATE "C" NOT NULL,
  revision BIGINT NOT NULL,
  as_of TEXT COLLATE "C" NOT NULL,
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

CREATE INDEX IF NOT EXISTS ix_cur_cost_snapshot_value_code_as_of ON cur_cost_snapshot_value (cost_code_id, as_of);

CREATE INDEX IF NOT EXISTS ix_cur_cost_snapshot_value_snapshot ON cur_cost_snapshot_value (snapshot_id, code);
