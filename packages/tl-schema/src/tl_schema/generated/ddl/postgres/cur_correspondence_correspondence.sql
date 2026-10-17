CREATE TABLE IF NOT EXISTS cur_correspondence_correspondence (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  number TEXT COLLATE "C" NOT NULL,
  direction TEXT COLLATE "C" NOT NULL,
  medium TEXT COLLATE "C" NOT NULL,
  received_via TEXT COLLATE "C" NOT NULL,
  external_ref TEXT COLLATE "C",
  message_id TEXT COLLATE "C",
  in_reply_to TEXT COLLATE "C",
  from_party_id TEXT COLLATE "C",
  from_name TEXT COLLATE "C",
  to_json_json JSONB NOT NULL DEFAULT '{}',
  cc_json_json JSONB NOT NULL DEFAULT '{}',
  sent_on TEXT COLLATE "C",
  received_on TEXT COLLATE "C",
  issued_on TEXT COLLATE "C",
  body TEXT COLLATE "C",
  confidentiality TEXT COLLATE "C" NOT NULL DEFAULT 'internal',
  domain TEXT COLLATE "C",
  subtype TEXT COLLATE "C",
  thread_id TEXT COLLATE "C",
  responds_to_id TEXT COLLATE "C",
  superseded_by_id TEXT COLLATE "C",
  response_required BOOLEAN NOT NULL DEFAULT FALSE,
  response_due TEXT COLLATE "C",
  responded_on TEXT COLLATE "C",
  triaged_on TEXT COLLATE "C",
  triaged_by TEXT COLLATE "C",
  rendition_file_id TEXT COLLATE "C",
  rendition_sha256 TEXT COLLATE "C",
  delivery TEXT COLLATE "C" NOT NULL DEFAULT 'none',
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_message_id ON cur_correspondence_correspondence (scope, message_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_class ON cur_correspondence_correspondence (scope, confidentiality);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_direction ON cur_correspondence_correspondence (scope, direction);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_domain ON cur_correspondence_correspondence (scope, domain);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_due ON cur_correspondence_correspondence (scope, response_due);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_received ON cur_correspondence_correspondence (scope, received_on);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_thread ON cur_correspondence_correspondence (thread_id);
