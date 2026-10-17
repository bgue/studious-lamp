CREATE TABLE IF NOT EXISTS job_queue (
  job_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  scope TEXT NOT NULL,
  state TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,
  attempt INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  run_after TEXT NOT NULL,
  lease_owner TEXT,
  lease_until TEXT,
  enqueued_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS ix_job_queue_claim ON job_queue (state, run_after);

CREATE INDEX IF NOT EXISTS ix_job_queue_scope_state ON job_queue (scope, state);
