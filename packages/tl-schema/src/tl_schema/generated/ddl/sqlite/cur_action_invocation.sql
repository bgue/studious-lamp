CREATE TABLE IF NOT EXISTS cur_action_invocation (
  invocation_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  action TEXT NOT NULL,
  action_version INTEGER NOT NULL,
  definition_id TEXT NOT NULL,
  status TEXT NOT NULL,
  targets_json TEXT NOT NULL DEFAULT '{}',
  parameters_json TEXT NOT NULL DEFAULT '{}',
  invoked_by TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 0,
  requested_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  result_json TEXT,
  http_status INTEGER,
  problems_json TEXT,
  proposal_id TEXT,
  seq INTEGER NOT NULL,
  version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_action_invocation_scope ON cur_action_invocation (scope);

CREATE INDEX IF NOT EXISTS ix_cur_action_invocation_status ON cur_action_invocation (status);

CREATE INDEX IF NOT EXISTS ix_cur_action_invocation_action_seq ON cur_action_invocation (action, seq DESC);
