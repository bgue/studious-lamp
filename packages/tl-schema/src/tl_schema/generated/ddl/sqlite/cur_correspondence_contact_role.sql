CREATE TABLE IF NOT EXISTS cur_correspondence_contact_role (
  contact_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  party_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  name TEXT NOT NULL,
  email TEXT,
  title TEXT,
  domain TEXT,
  is_authorised INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_contact_role_email ON cur_correspondence_contact_role (scope, email);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_contact_role_party ON cur_correspondence_contact_role (party_id);
