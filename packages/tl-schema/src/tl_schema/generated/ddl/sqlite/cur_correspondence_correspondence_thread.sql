CREATE TABLE IF NOT EXISTS cur_correspondence_correspondence_thread (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  number TEXT NOT NULL,
  subject_key TEXT NOT NULL,
  domain TEXT,
  state TEXT NOT NULL DEFAULT 'open',
  governing_item_id TEXT,
  item_count INTEGER NOT NULL DEFAULT 0,
  last_item_on TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_thread_scope_state ON cur_correspondence_correspondence_thread (scope, state);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_thread_scope_subject ON cur_correspondence_correspondence_thread (scope, subject_key);
