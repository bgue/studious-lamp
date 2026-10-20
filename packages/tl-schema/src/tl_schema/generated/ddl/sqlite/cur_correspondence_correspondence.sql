CREATE TABLE IF NOT EXISTS cur_correspondence_correspondence (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  number TEXT NOT NULL,
  direction TEXT NOT NULL,
  medium TEXT NOT NULL,
  received_via TEXT NOT NULL,
  external_ref TEXT,
  message_id TEXT,
  in_reply_to TEXT,
  from_party_id TEXT,
  from_name TEXT,
  to_parties_json TEXT NOT NULL DEFAULT '{}',
  cc_parties_json TEXT NOT NULL DEFAULT '{}',
  sent_on TEXT,
  received_on TEXT,
  issued_on TEXT,
  body TEXT,
  confidentiality TEXT NOT NULL DEFAULT 'internal',
  domain TEXT,
  subtype TEXT,
  thread_id TEXT,
  responds_to_id TEXT,
  superseded_by_id TEXT,
  response_required INTEGER NOT NULL DEFAULT 0,
  response_due TEXT,
  responded_on TEXT,
  triaged_on TEXT,
  triaged_by TEXT,
  rendition_file_id TEXT,
  rendition_sha256 TEXT,
  delivery TEXT NOT NULL DEFAULT 'none',
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_message_id ON cur_correspondence_correspondence (scope, message_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_class ON cur_correspondence_correspondence (scope, confidentiality);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_direction ON cur_correspondence_correspondence (scope, direction);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_domain ON cur_correspondence_correspondence (scope, domain);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_due ON cur_correspondence_correspondence (scope, response_due);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_scope_received ON cur_correspondence_correspondence (scope, received_on);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_thread ON cur_correspondence_correspondence (thread_id);
