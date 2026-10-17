CREATE TABLE IF NOT EXISTS job_queue (
  job_id TEXT COLLATE "C" PRIMARY KEY,
  kind TEXT COLLATE "C" NOT NULL,
  scope TEXT COLLATE "C" NOT NULL,
  state TEXT COLLATE "C" NOT NULL,
  priority BIGINT NOT NULL DEFAULT 0,
  attempt BIGINT NOT NULL DEFAULT 0,
  max_attempts BIGINT NOT NULL DEFAULT 3,
  run_after TEXT COLLATE "C" NOT NULL,
  lease_owner TEXT COLLATE "C",
  lease_until TEXT COLLATE "C",
  enqueued_at TEXT COLLATE "C" NOT NULL,
  started_at TEXT COLLATE "C",
  finished_at TEXT COLLATE "C",
  last_error TEXT COLLATE "C"
);

CREATE INDEX IF NOT EXISTS ix_job_queue_claim ON job_queue (state, run_after);

CREATE INDEX IF NOT EXISTS ix_job_queue_scope_state ON job_queue (scope, state);
