CREATE TABLE IF NOT EXISTS cur_documents_processing_job (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  derived_id TEXT COLLATE "C" NOT NULL,
  derived_key TEXT COLLATE "C" NOT NULL,
  source_ref TEXT COLLATE "C" NOT NULL,
  source_file_id TEXT COLLATE "C",
  extractor TEXT COLLATE "C",
  options_json JSONB NOT NULL DEFAULT '{}',
  schema_id TEXT COLLATE "C" NOT NULL,
  requested_by TEXT COLLATE "C" NOT NULL,
  state TEXT COLLATE "C" NOT NULL DEFAULT 'queued',
  attempt BIGINT NOT NULL DEFAULT 0,
  max_attempts BIGINT NOT NULL DEFAULT 3,
  worker TEXT COLLATE "C",
  started_at TEXT COLLATE "C",
  finished_at TEXT COLLATE "C",
  error_code TEXT COLLATE "C",
  error_message TEXT COLLATE "C",
  result_json JSONB,
  created_seq BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_processing_job_derived ON cur_documents_processing_job (derived_id, created_seq);

CREATE INDEX IF NOT EXISTS ix_cur_documents_processing_job_scope_state ON cur_documents_processing_job (scope, state);
