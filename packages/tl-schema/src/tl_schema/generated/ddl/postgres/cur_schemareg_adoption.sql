CREATE TABLE IF NOT EXISTS cur_schemareg_adoption (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  project TEXT COLLATE "C" NOT NULL,
  package TEXT COLLATE "C" NOT NULL,
  semver TEXT COLLATE "C" NOT NULL,
  previous_semver TEXT COLLATE "C",
  worst_class TEXT COLLATE "C",
  impact_sha256 TEXT COLLATE "C",
  adopted_by TEXT COLLATE "C" NOT NULL,
  adopted_at TEXT COLLATE "C" NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_schemareg_adoption_scope_package ON cur_schemareg_adoption (scope, package);

CREATE INDEX IF NOT EXISTS ix_cur_schemareg_adoption_scope_package ON cur_schemareg_adoption (scope, package);
