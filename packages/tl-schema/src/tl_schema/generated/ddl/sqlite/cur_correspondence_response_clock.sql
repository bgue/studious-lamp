CREATE TABLE IF NOT EXISTS cur_correspondence_response_clock (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  item_id TEXT NOT NULL,
  item_number TEXT NOT NULL,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  start_on TEXT NOT NULL,
  duration_days INTEGER NOT NULL,
  day_type TEXT NOT NULL,
  calendar TEXT NOT NULL,
  warn_days_json_json TEXT NOT NULL DEFAULT '{}',
  due_on TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'running',
  paused_on TEXT,
  pause_reason TEXT,
  closed_on TEXT,
  closed_reason TEXT,
  warned_level INTEGER,
  owner TEXT,
  clause_id TEXT,
  restarts INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_response_clock_clause ON cur_correspondence_response_clock (clause_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_response_clock_item ON cur_correspondence_response_clock (item_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_response_clock_scope_state_due ON cur_correspondence_response_clock (scope, state, due_on);
