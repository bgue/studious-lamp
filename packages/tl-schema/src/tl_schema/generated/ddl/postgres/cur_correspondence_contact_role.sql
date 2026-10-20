CREATE TABLE IF NOT EXISTS cur_correspondence_contact_role (
  contact_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  party_id TEXT COLLATE "C" NOT NULL,
  position BIGINT NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  email TEXT COLLATE "C",
  title TEXT COLLATE "C",
  domain TEXT COLLATE "C",
  is_authorised BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_contact_role_email ON cur_correspondence_contact_role (scope, email);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_contact_role_party ON cur_correspondence_contact_role (party_id);
