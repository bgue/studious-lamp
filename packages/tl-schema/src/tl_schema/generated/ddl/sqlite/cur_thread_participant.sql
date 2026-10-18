CREATE TABLE IF NOT EXISTS cur_thread_participant (
  participant_row_id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  reasons_json TEXT NOT NULL DEFAULT '{}',
  first_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_thread_participant_record_id ON cur_thread_participant (record_id);
