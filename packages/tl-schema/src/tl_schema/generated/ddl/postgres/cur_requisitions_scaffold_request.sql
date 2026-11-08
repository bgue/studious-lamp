CREATE TABLE IF NOT EXISTS cur_requisitions_scaffold_request (
  purpose TEXT COLLATE "C" NOT NULL,
  elevation TEXT COLLATE "C",
  gridline TEXT COLLATE "C",
  length_m TEXT COLLATE "C",
  width_m TEXT COLLATE "C",
  height_m TEXT COLLATE "C",
  load_class TEXT COLLATE "C",
  duration_days BIGINT NOT NULL,
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

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_scaffold_request_for_record ON cur_requisitions_scaffold_request (for_record_id);

CREATE INDEX IF NOT EXISTS ix_cur_requisitions_scaffold_request_scope_kind ON cur_requisitions_scaffold_request (scope, kind);
