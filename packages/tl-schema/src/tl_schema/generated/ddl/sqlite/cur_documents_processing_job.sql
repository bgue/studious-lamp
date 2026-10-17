CREATE TABLE IF NOT EXISTS cur_documents_processing_job (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  kind TEXT NOT NULL,
  derived_id TEXT NOT NULL,
  derived_key TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  source_file_id TEXT,
  extractor TEXT,
  options_json TEXT NOT NULL DEFAULT '{}',
  schema_id TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'queued',
  attempt INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  worker TEXT,
  started_at TEXT,
  finished_at TEXT,
  error_code TEXT,
  error_message TEXT,
  result_json TEXT,
  created_seq INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_processing_job_derived ON cur_documents_processing_job (derived_id, created_seq);

CREATE INDEX IF NOT EXISTS ix_cur_documents_processing_job_scope_state ON cur_documents_processing_job (scope, state);
