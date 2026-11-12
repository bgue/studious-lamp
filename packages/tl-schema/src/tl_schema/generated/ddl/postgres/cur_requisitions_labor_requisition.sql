CREATE TABLE IF NOT EXISTS cur_requisitions_labor_requisition (
  craft TEXT COLLATE "C" NOT NULL,
  classification TEXT COLLATE "C",
  headcount BIGINT NOT NULL,
  start_date TEXT COLLATE "C" NOT NULL,
  end_date TEXT COLLATE "C" NOT NULL,
  shift TEXT COLLATE "C",
  requirements TEXT COLLATE "C",
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  kind TEXT COLLATE "C" NOT NULL,
  subject TEXT COLLATE "C" NOT NULL,
  requester TEXT COLLATE "C" NOT NULL,
  need_by TEXT COLLATE "C",
  location_text TEXT COLLATE "C",
  priority TEXT COLLATE "C" NOT NULL,
  for_record_id TEXT COLLATE "C",
  approved_by TEXT COLLATE "C",
  approved_at TEXT COLLATE "C",
  reject_reason TEXT COLLATE "C",
  work_order_id TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_labor_requisition_craft_start ON cur_requisitions_labor_requisition (craft, start_date);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_labor_requisition_for_record ON cur_requisitions_labor_requisition (for_record_id);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_labor_requisition_scope_kind ON cur_requisitions_labor_requisition (scope, kind);
