CREATE TABLE IF NOT EXISTS cur_proposals (
  proposal_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  tool TEXT NOT NULL,
  agent TEXT NOT NULL,
  command_type TEXT NOT NULL,
  command_json TEXT NOT NULL DEFAULT '{}',
  summary TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_day TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_event_id TEXT NOT NULL,
  decided_by TEXT,
  decided_at TEXT,
  reason TEXT,
  result_stream_id TEXT,
  seq INTEGER NOT NULL,
  version INTEGER
);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_scope ON cur_proposals (scope);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_agent ON cur_proposals (agent);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_status ON cur_proposals (status);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_created_day ON cur_proposals (created_day);

CREATE INDEX IF NOT EXISTS ix_cur_proposals_seq ON cur_proposals (seq);
