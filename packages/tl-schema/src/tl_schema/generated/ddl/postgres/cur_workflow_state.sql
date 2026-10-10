CREATE TABLE IF NOT EXISTS cur_workflow_state (
  record_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  workflow TEXT COLLATE "C" NOT NULL,
  workflow_version BIGINT NOT NULL,
  state TEXT COLLATE "C" NOT NULL,
  entered_at TIMESTAMPTZ NOT NULL,
  transition TEXT COLLATE "C" NOT NULL,
  transitioned_by TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_workflow_state_state ON cur_workflow_state (state);
