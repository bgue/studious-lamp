CREATE TABLE IF NOT EXISTS cur_legacy_load_run (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  source_system TEXT NOT NULL,
  source_table TEXT NOT NULL,
  run_number INTEGER NOT NULL,
  loader TEXT NOT NULL,
  confidentiality TEXT,
  source_name TEXT,
  source_sha256 TEXT,
  source_size INTEGER,
  row_count INTEGER,
  column_count INTEGER,
  extracted_file_id TEXT,
  extracted_sha256 TEXT,
  profile_file_id TEXT,
  profile_sha256 TEXT,
  bronze_rows INTEGER,
  mapping_name TEXT,
  mapping_sha256 TEXT,
  plan_new INTEGER,
  plan_existing INTEGER,
  plan_invalid INTEGER,
  loaded_count INTEGER,
  record_ids TEXT,
  correlation_id TEXT,
  report_file_id TEXT,
  report_sha256 TEXT,
  report_document_id TEXT,
  mismatches INTEGER,
  opened_by TEXT NOT NULL,
  last_error TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_legacy_load_run_scope_system_table_number ON cur_legacy_load_run (scope, source_system, source_table, run_number);

CREATE INDEX IF NOT EXISTS ix_cur_legacy_load_run_scope_system ON cur_legacy_load_run (scope, source_system, source_table);
