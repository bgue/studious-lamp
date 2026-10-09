CREATE TABLE IF NOT EXISTS cur_workflow_state (
  record_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  workflow TEXT NOT NULL,
  workflow_version BIGINT NOT NULL,
  state TEXT NOT NULL,
  entered_at TIMESTAMPTZ NOT NULL,
  transition TEXT NOT NULL,
  transitioned_by TEXT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_workflow_state_state ON cur_workflow_state (state);
