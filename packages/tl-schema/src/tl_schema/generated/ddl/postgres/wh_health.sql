CREATE TABLE IF NOT EXISTS wh_health (
  subscription_id TEXT PRIMARY KEY,
  consecutive_dead BIGINT NOT NULL DEFAULT 0,
  failing_since TEXT,
  last_success_at TEXT,
  last_failure_at TEXT,
  delivered_total BIGINT NOT NULL DEFAULT 0,
  failed_total BIGINT NOT NULL DEFAULT 0
);
