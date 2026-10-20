CREATE TABLE IF NOT EXISTS cur_schemareg_schema_package (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  package TEXT COLLATE "C" NOT NULL,
  semver TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  project TEXT COLLATE "C",
  package_title TEXT COLLATE "C",
  content TEXT COLLATE "C" NOT NULL,
  content_sha256 TEXT COLLATE "C" NOT NULL,
  changelog TEXT COLLATE "C",
  drafted_by TEXT COLLATE "C" NOT NULL,
  base_ref TEXT COLLATE "C",
  classification TEXT COLLATE "C",
  classification_digest TEXT COLLATE "C",
  worst_class TEXT COLLATE "C",
  impact TEXT COLLATE "C",
  impact_sha256 TEXT COLLATE "C",
  analysed_sha256 TEXT COLLATE "C",
  submitted_by TEXT COLLATE "C",
  approved_by TEXT COLLATE "C",
  approved_digest TEXT COLLATE "C",
  published_at TEXT COLLATE "C",
  deprecated_at TEXT COLLATE "C",
  retired_at TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_schemareg_schema_package_package_version ON cur_schemareg_schema_package (package, semver);

CREATE INDEX IF NOT EXISTS ix_cur_schemareg_schema_package_scope_package ON cur_schemareg_schema_package (scope, package, semver);
