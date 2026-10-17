CREATE TABLE IF NOT EXISTS cur_correspondence_party (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  project_role TEXT NOT NULL,
  email_domains_json TEXT NOT NULL DEFAULT '{}',
  is_active INTEGER NOT NULL DEFAULT 1,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_party_scope_role ON cur_correspondence_party (scope, project_role);
