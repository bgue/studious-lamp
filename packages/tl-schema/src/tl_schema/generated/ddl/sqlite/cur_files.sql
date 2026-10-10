CREATE TABLE IF NOT EXISTS cur_files (
  file_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  record_id TEXT NOT NULL,
  slot TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  sha256 TEXT NOT NULL,
  size INTEGER NOT NULL,
  content_type TEXT NOT NULL,
  filename TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'quarantined',
  deduplicated INTEGER NOT NULL DEFAULT 0,
  superseded_by TEXT,
  report_json TEXT,
  reason TEXT,
  uploaded_by TEXT NOT NULL,
  uploaded_at TEXT NOT NULL,
  processed_at TEXT,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_files_scope ON cur_files (scope);

CREATE INDEX IF NOT EXISTS ix_cur_files_record_id ON cur_files (record_id);

CREATE INDEX IF NOT EXISTS ix_cur_files_sha256 ON cur_files (sha256);
