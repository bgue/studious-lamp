CREATE TABLE IF NOT EXISTS wh_health (
  subscription_id TEXT COLLATE "C" PRIMARY KEY,
  consecutive_dead BIGINT NOT NULL DEFAULT 0,
  failing_since TEXT COLLATE "C",
  last_success_at TEXT COLLATE "C",
  last_failure_at TEXT COLLATE "C",
  delivered_total BIGINT NOT NULL DEFAULT 0,
  failed_total BIGINT NOT NULL DEFAULT 0
);
