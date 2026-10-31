CREATE TABLE IF NOT EXISTS cur_account_module_role (
  account_id TEXT COLLATE "C" NOT NULL,
  project TEXT COLLATE "C" NOT NULL,
  module TEXT COLLATE "C" NOT NULL,
  role TEXT COLLATE "C" NOT NULL,
  granted_by TEXT COLLATE "C" NOT NULL,
  granted_at TEXT COLLATE "C" NOT NULL,
  seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_account_module_role_grant ON cur_account_module_role (account_id, project, module, role);

CREATE INDEX IF NOT EXISTS ix_cur_account_module_role_scope ON cur_account_module_role (project, module);
