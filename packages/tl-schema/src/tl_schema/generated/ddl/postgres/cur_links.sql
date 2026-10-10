CREATE TABLE IF NOT EXISTS cur_links (
  link_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  from_id TEXT COLLATE "C" NOT NULL,
  to_id TEXT COLLATE "C" NOT NULL,
  relation TEXT COLLATE "C" NOT NULL,
  status TEXT COLLATE "C" NOT NULL DEFAULT 'active',
  pin TEXT COLLATE "C",
  note TEXT COLLATE "C",
  source TEXT COLLATE "C" NOT NULL,
  confidence DOUBLE PRECISION,
  reason TEXT COLLATE "C",
  declined BOOLEAN NOT NULL DEFAULT FALSE,
  verified_by TEXT COLLATE "C",
  verified_at TIMESTAMPTZ,
  created_by TEXT COLLATE "C" NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_links_scope ON cur_links (scope);

CREATE INDEX IF NOT EXISTS ix_cur_links_from_id ON cur_links (from_id);

CREATE INDEX IF NOT EXISTS ix_cur_links_to_id ON cur_links (to_id);
