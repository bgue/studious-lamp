CREATE TABLE IF NOT EXISTS cur_thread_participant (
  participant_row_id TEXT COLLATE "C" PRIMARY KEY,
  record_id TEXT COLLATE "C" NOT NULL,
  actor TEXT COLLATE "C" NOT NULL,
  reasons_json JSONB NOT NULL DEFAULT '{}',
  first_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_thread_participant_record_id ON cur_thread_participant (record_id);
