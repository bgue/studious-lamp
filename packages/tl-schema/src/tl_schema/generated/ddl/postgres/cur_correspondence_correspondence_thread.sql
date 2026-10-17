CREATE TABLE IF NOT EXISTS cur_correspondence_correspondence_thread (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  number TEXT COLLATE "C" NOT NULL,
  subject_key TEXT COLLATE "C" NOT NULL,
  domain TEXT COLLATE "C",
  state TEXT COLLATE "C" NOT NULL DEFAULT 'open',
  governing_item_id TEXT COLLATE "C",
  item_count BIGINT NOT NULL DEFAULT 0,
  last_item_on TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_thread_scope_state ON cur_correspondence_correspondence_thread (scope, state);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_thread_scope_subject ON cur_correspondence_correspondence_thread (scope, subject_key);
