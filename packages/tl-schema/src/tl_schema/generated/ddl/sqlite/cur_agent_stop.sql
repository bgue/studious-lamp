CREATE TABLE IF NOT EXISTS cur_agent_stop (
  agent TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  stopped INTEGER NOT NULL DEFAULT 0,
  stopped_at TEXT,
  stopped_by TEXT,
  reason TEXT,
  resumed_at TEXT,
  resumed_by TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_agent_stop_stopped ON cur_agent_stop (stopped);
