CREATE TABLE IF NOT EXISTS cur_schemareg_schema_package (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  package TEXT NOT NULL,
  semver TEXT NOT NULL,
  kind TEXT NOT NULL,
  project TEXT,
  package_title TEXT,
  content TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  changelog TEXT,
  drafted_by TEXT NOT NULL,
  base_ref TEXT,
  classification TEXT,
  classification_digest TEXT,
  worst_class TEXT,
  impact TEXT,
  impact_sha256 TEXT,
  analysed_sha256 TEXT,
  submitted_by TEXT,
  approved_by TEXT,
  approved_digest TEXT,
  published_at TEXT,
  deprecated_at TEXT,
  retired_at TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_schemareg_schema_package_package_version ON cur_schemareg_schema_package (package, semver);

CREATE INDEX IF NOT EXISTS ix_cur_schemareg_schema_package_scope_package ON cur_schemareg_schema_package (scope, package, semver);
