CREATE TABLE IF NOT EXISTS cur_schemareg_adoption (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  project TEXT NOT NULL,
  package TEXT NOT NULL,
  semver TEXT NOT NULL,
  previous_semver TEXT,
  worst_class TEXT,
  impact_sha256 TEXT,
  adopted_by TEXT NOT NULL,
  adopted_at TEXT NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_schemareg_adoption_scope_package ON cur_schemareg_adoption (scope, package);

CREATE INDEX IF NOT EXISTS ix_cur_schemareg_adoption_scope_package ON cur_schemareg_adoption (scope, package);
