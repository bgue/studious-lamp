CREATE TABLE IF NOT EXISTS rule_firing (
  firing_id TEXT COLLATE "C" PRIMARY KEY,
  rule_id TEXT COLLATE "C" NOT NULL,
  rule_version BIGINT NOT NULL,
  event_id TEXT COLLATE "C" NOT NULL,
  seq BIGINT NOT NULL,
  depth BIGINT NOT NULL,
  outcome TEXT COLLATE "C" NOT NULL,
  command_count BIGINT NOT NULL DEFAULT 0,
  fired_at TEXT COLLATE "C" NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_rule_firing_event ON rule_firing (event_id);

CREATE INDEX IF NOT EXISTS ix_rule_firing_rule_seq ON rule_firing (rule_id, seq DESC);
