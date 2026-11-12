CREATE TABLE IF NOT EXISTS cur_requisitions_scaffold_request (
  purpose TEXT NOT NULL,
  elevation TEXT,
  gridline TEXT,
  length_m TEXT,
  width_m TEXT,
  height_m TEXT,
  load_class TEXT,
  duration_days INTEGER NOT NULL,
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  kind TEXT NOT NULL,
  subject TEXT NOT NULL,
  requester TEXT NOT NULL,
  need_by TEXT,
  location_text TEXT,
  priority TEXT NOT NULL,
  for_record_id TEXT,
  approved_by TEXT,
  approved_at TEXT,
  reject_reason TEXT,
  work_order_id TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_scaffold_request_for_record ON cur_requisitions_scaffold_request (for_record_id);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_scaffold_request_scope_kind ON cur_requisitions_scaffold_request (scope, kind);
