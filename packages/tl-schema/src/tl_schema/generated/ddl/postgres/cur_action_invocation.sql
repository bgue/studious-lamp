CREATE TABLE IF NOT EXISTS cur_action_invocation (
  invocation_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  action TEXT COLLATE "C" NOT NULL,
  action_version BIGINT NOT NULL,
  definition_id TEXT COLLATE "C" NOT NULL,
  status TEXT COLLATE "C" NOT NULL,
  targets_json JSONB NOT NULL DEFAULT '{}',
  parameters_json JSONB NOT NULL DEFAULT '{}',
  invoked_by TEXT COLLATE "C" NOT NULL,
  attempt BIGINT NOT NULL DEFAULT 0,
  requested_at TIMESTAMPTZ NOT NULL,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  result_json JSONB,
  http_status BIGINT,
  problems_json JSONB,
  proposal_id TEXT COLLATE "C",
  seq BIGINT NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_action_invocation_scope ON cur_action_invocation (scope);

CREATE INDEX IF NOT EXISTS ix_cur_action_invocation_status ON cur_action_invocation (status);

CREATE INDEX IF NOT EXISTS ix_cur_action_invocation_action_seq ON cur_action_invocation (action, seq DESC);
