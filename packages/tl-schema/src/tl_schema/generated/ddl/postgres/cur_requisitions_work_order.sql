CREATE TABLE IF NOT EXISTS cur_requisitions_work_order (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  requisition_id TEXT COLLATE "C" NOT NULL,
  work_kind TEXT COLLATE "C" NOT NULL,
  assigned_to TEXT COLLATE "C",
  planned_start TEXT COLLATE "C",
  planned_finish TEXT COLLATE "C",
  actual_start TEXT COLLATE "C",
  actual_finish TEXT COLLATE "C",
  hours_planned TEXT COLLATE "C",
  hours_actual TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_work_order_requisition ON cur_requisitions_work_order (requisition_id);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_work_order_scope_assignee ON cur_requisitions_work_order (scope, assigned_to);
