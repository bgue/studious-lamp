CREATE TABLE IF NOT EXISTS cur_proposals (
  proposal_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  tool TEXT COLLATE "C" NOT NULL,
  agent TEXT COLLATE "C" NOT NULL,
  command_type TEXT COLLATE "C" NOT NULL,
  command_json JSONB NOT NULL DEFAULT '{}',
  summary TEXT COLLATE "C" NOT NULL,
  status TEXT COLLATE "C" NOT NULL DEFAULT 'pending',
  created_day TEXT COLLATE "C" NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  created_event_id TEXT COLLATE "C" NOT NULL,
  decided_by TEXT COLLATE "C",
  decided_at TIMESTAMPTZ,
  reason TEXT COLLATE "C",
  result_stream_id TEXT COLLATE "C",
  seq BIGINT NOT NULL,
  version BIGINT
);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_scope ON cur_proposals (scope);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_agent ON cur_proposals (agent);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_status ON cur_proposals (status);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_created_day ON cur_proposals (created_day);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_seq ON cur_proposals (seq);
