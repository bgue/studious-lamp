CREATE TABLE IF NOT EXISTS cur_requisitions_general_requisition (
  general_type TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_general_requisition_for_record ON cur_requisitions_general_requisition (for_record_id);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_general_requisition_scope_kind ON cur_requisitions_general_requisition (scope, kind);
