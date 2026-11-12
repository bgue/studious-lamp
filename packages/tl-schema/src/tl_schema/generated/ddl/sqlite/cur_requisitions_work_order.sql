CREATE TABLE IF NOT EXISTS cur_requisitions_work_order (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  requisition_id TEXT NOT NULL,
  work_kind TEXT NOT NULL,
  assigned_to TEXT,
  planned_start TEXT,
  planned_finish TEXT,
  actual_start TEXT,
  actual_finish TEXT,
  hours_planned TEXT,
  hours_actual TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_work_order_requisition ON cur_requisitions_work_order (requisition_id);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_work_order_scope_assignee ON cur_requisitions_work_order (scope, assigned_to);
