CREATE TABLE IF NOT EXISTS cur_correspondence_party (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  project_role TEXT COLLATE "C" NOT NULL,
  email_domains_json_json JSONB NOT NULL DEFAULT '{}',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_party_scope_role ON cur_correspondence_party (scope, project_role);
