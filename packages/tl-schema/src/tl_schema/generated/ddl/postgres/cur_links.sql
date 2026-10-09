CREATE TABLE IF NOT EXISTS cur_links (
  link_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  from_id TEXT NOT NULL,
  to_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  pin TEXT,
  note TEXT,
  source TEXT NOT NULL,
  confidence DOUBLE PRECISION,
  reason TEXT,
  declined BOOLEAN NOT NULL DEFAULT FALSE,
  verified_by TEXT,
  verified_at TIMESTAMPTZ,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_links_scope ON cur_links (scope);

CREATE INDEX IF NOT EXISTS ix_cur_links_from_id ON cur_links (from_id);

CREATE INDEX IF NOT EXISTS ix_cur_links_to_id ON cur_links (to_id);
