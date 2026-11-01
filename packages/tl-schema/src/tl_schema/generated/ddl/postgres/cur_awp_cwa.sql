CREATE TABLE IF NOT EXISTS cur_awp_cwa (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code TEXT COLLATE "C" NOT NULL,
  location_text TEXT COLLATE "C",
  retired BOOLEAN NOT NULL DEFAULT FALSE,
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_awp_cwa_scope_code ON cur_awp_cwa (scope, code);
