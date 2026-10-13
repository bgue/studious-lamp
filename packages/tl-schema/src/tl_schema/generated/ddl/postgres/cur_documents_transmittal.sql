CREATE TABLE IF NOT EXISTS cur_documents_transmittal (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  number TEXT COLLATE "C" NOT NULL,
  direction TEXT COLLATE "C" NOT NULL,
  purpose TEXT COLLATE "C" NOT NULL,
  due_date TEXT COLLATE "C",
  issued_on TEXT COLLATE "C",
  response_code TEXT COLLATE "C",
  response_note TEXT COLLATE "C",
  responded_on TEXT COLLATE "C",
  recipients_json JSONB NOT NULL DEFAULT '{}',
  item_count BIGINT NOT NULL DEFAULT 0,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_transmittal_scope_direction ON cur_documents_transmittal (scope, direction);

CREATE INDEX IF NOT EXISTS ix_cur_documents_transmittal_scope_due ON cur_documents_transmittal (scope, due_date);
