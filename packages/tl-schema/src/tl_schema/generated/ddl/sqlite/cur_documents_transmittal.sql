CREATE TABLE IF NOT EXISTS cur_documents_transmittal (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  number TEXT NOT NULL,
  direction TEXT NOT NULL,
  purpose TEXT NOT NULL,
  due_date TEXT,
  issued_on TEXT,
  response_code TEXT,
  response_note TEXT,
  responded_on TEXT,
  recipients_json TEXT NOT NULL DEFAULT '{}',
  item_count INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_documents_transmittal_scope_direction ON cur_documents_transmittal (scope, direction);

CREATE INDEX IF NOT EXISTS ix_cur_documents_transmittal_scope_due ON cur_documents_transmittal (scope, due_date);
