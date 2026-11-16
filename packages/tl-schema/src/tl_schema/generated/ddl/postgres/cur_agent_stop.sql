CREATE TABLE IF NOT EXISTS cur_agent_stop (
  agent TEXT COLLATE "C" PRIMARY KEY,
  account_id TEXT COLLATE "C" NOT NULL,
  stopped BIGINT NOT NULL DEFAULT 0,
  stopped_at TEXT COLLATE "C",
  stopped_by TEXT COLLATE "C",
  reason TEXT COLLATE "C",
  resumed_at TEXT COLLATE "C",
  resumed_by TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_agent_stop_stopped ON cur_agent_stop (stopped);
