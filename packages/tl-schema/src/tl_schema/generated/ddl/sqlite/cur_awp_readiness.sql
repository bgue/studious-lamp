CREATE TABLE IF NOT EXISTS cur_awp_readiness (
  iwp_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  evaluated_at TEXT NOT NULL,
  today TEXT NOT NULL,
  ready INTEGER NOT NULL,
  facts_hash TEXT NOT NULL,
  as_of_seq INTEGER NOT NULL
);
