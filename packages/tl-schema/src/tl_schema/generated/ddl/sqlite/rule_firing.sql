CREATE TABLE IF NOT EXISTS rule_firing (
  firing_id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL,
  rule_version INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  depth INTEGER NOT NULL,
  outcome TEXT NOT NULL,
  command_count INTEGER NOT NULL DEFAULT 0,
  fired_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_rule_firing_event ON rule_firing (event_id);

CREATE INDEX IF NOT EXISTS ix_rule_firing_rule_seq ON rule_firing (rule_id, seq DESC);
