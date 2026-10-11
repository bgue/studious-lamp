CREATE TABLE IF NOT EXISTS setting_effect_applied (
  effect TEXT COLLATE "C" PRIMARY KEY,
  applied_seq BIGINT NOT NULL,
  applied_us BIGINT NOT NULL,
  applied_by TEXT COLLATE "C" NOT NULL
);
