CREATE TABLE IF NOT EXISTS cur_requisitions_labor_requisition (
  craft TEXT NOT NULL,
  classification TEXT,
  headcount INTEGER NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  shift TEXT,
  requirements TEXT,
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

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_labor_requisition_craft_start ON cur_requisitions_labor_requisition (craft, start_date);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_labor_requisition_for_record ON cur_requisitions_labor_requisition (for_record_id);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_labor_requisition_scope_kind ON cur_requisitions_labor_requisition (scope, kind);
