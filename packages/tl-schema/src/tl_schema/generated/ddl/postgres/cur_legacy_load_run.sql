CREATE TABLE IF NOT EXISTS cur_legacy_load_run (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  source_system TEXT COLLATE "C" NOT NULL,
  source_table TEXT COLLATE "C" NOT NULL,
  run_number BIGINT NOT NULL,
  loader TEXT COLLATE "C" NOT NULL,
  source_name TEXT COLLATE "C",
  source_sha256 TEXT COLLATE "C",
  source_size BIGINT,
  row_count BIGINT,
  column_count BIGINT,
  extracted_file_id TEXT COLLATE "C",
  extracted_sha256 TEXT COLLATE "C",
  profile_file_id TEXT COLLATE "C",
  profile_sha256 TEXT COLLATE "C",
  bronze_rows BIGINT,
  mapping_name TEXT COLLATE "C",
  mapping_sha256 TEXT COLLATE "C",
  plan_new BIGINT,
  plan_existing BIGINT,
  plan_invalid BIGINT,
  loaded_count BIGINT,
  record_ids TEXT COLLATE "C",
  correlation_id TEXT COLLATE "C",
  report_file_id TEXT COLLATE "C",
  report_sha256 TEXT COLLATE "C",
  report_document_id TEXT COLLATE "C",
  mismatches BIGINT,
  opened_by TEXT COLLATE "C" NOT NULL,
  last_error TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_legacy_load_run_scope_system_table_number ON cur_legacy_load_run (scope, source_system, source_table, run_number);

CREATE INDEX IF NOT EXISTS ix_cur_legacy_load_run_scope_system ON cur_legacy_load_run (scope, source_system, source_table);
