CREATE TABLE IF NOT EXISTS cur_awp_readiness (
  iwp_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  evaluated_at TEXT COLLATE "C" NOT NULL,
  today TEXT COLLATE "C" NOT NULL,
  ready BOOLEAN NOT NULL,
  facts_hash TEXT COLLATE "C" NOT NULL,
  as_of_seq BIGINT NOT NULL
);
