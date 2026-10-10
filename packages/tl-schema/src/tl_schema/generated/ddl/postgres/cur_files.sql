CREATE TABLE IF NOT EXISTS cur_files (
  file_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  record_id TEXT COLLATE "C" NOT NULL,
  slot TEXT COLLATE "C",
  revision BIGINT NOT NULL DEFAULT 1,
  sha256 TEXT COLLATE "C" NOT NULL,
  size BIGINT NOT NULL,
  content_type TEXT COLLATE "C" NOT NULL,
  filename TEXT COLLATE "C" NOT NULL,
  status TEXT COLLATE "C" NOT NULL DEFAULT 'quarantined',
  deduplicated BOOLEAN NOT NULL DEFAULT FALSE,
  superseded_by TEXT COLLATE "C",
  report_json JSONB,
  reason TEXT COLLATE "C",
  uploaded_by TEXT COLLATE "C" NOT NULL,
  uploaded_at TIMESTAMPTZ NOT NULL,
  processed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_files_scope ON cur_files (scope);

CREATE INDEX IF NOT EXISTS ix_cur_files_record_id ON cur_files (record_id);

CREATE INDEX IF NOT EXISTS ix_cur_files_sha256 ON cur_files (sha256);
