CREATE TABLE IF NOT EXISTS cur_account_module_role (
  account_id TEXT NOT NULL,
  project TEXT NOT NULL,
  module TEXT NOT NULL,
  role TEXT NOT NULL,
  granted_by TEXT NOT NULL,
  granted_at TEXT NOT NULL,
  seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_account_module_role_grant ON cur_account_module_role (account_id, project, module, role);

CREATE INDEX IF NOT EXISTS ix_cur_account_module_role_scope ON cur_account_module_role (project, module);
