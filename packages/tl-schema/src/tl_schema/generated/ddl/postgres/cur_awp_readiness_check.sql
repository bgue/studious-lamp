CREATE TABLE IF NOT EXISTS cur_awp_readiness_check (
  row_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  iwp_id TEXT COLLATE "C" NOT NULL,
  name TEXT COLLATE "C" NOT NULL,
  version TEXT COLLATE "C" NOT NULL,
  state TEXT COLLATE "C" NOT NULL,
  detail TEXT COLLATE "C",
  count_ok BIGINT,
  count_total BIGINT,
  resolve_via_json JSONB,
  as_of_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_awp_readiness_check_iwp ON cur_awp_readiness_check (iwp_id);
