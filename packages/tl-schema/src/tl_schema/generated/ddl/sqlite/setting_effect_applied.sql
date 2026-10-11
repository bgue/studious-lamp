CREATE TABLE IF NOT EXISTS setting_effect_applied (
  effect TEXT PRIMARY KEY,
  applied_seq INTEGER NOT NULL,
  applied_us INTEGER NOT NULL,
  applied_by TEXT NOT NULL
);
