CREATE TABLE IF NOT EXISTS cur_correspondence_response_clock (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  item_id TEXT COLLATE "C" NOT NULL,
  item_number TEXT COLLATE "C" NOT NULL,
  label TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  start_on TEXT COLLATE "C" NOT NULL,
  duration_days BIGINT NOT NULL,
  day_type TEXT COLLATE "C" NOT NULL,
  calendar TEXT COLLATE "C" NOT NULL,
  warn_days_json JSONB NOT NULL DEFAULT '{}',
  due_on TEXT COLLATE "C" NOT NULL,
  state TEXT COLLATE "C" NOT NULL DEFAULT 'running',
  paused_on TEXT COLLATE "C",
  pause_reason TEXT COLLATE "C",
  closed_on TEXT COLLATE "C",
  closed_reason TEXT COLLATE "C",
  warned_level BIGINT,
  owner TEXT COLLATE "C",
  clause_id TEXT COLLATE "C",
  restarts BIGINT NOT NULL DEFAULT 0,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_response_clock_clause ON cur_correspondence_response_clock (clause_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_response_clock_item ON cur_correspondence_response_clock (item_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_response_clock_scope_state_due ON cur_correspondence_response_clock (scope, state, due_on);
