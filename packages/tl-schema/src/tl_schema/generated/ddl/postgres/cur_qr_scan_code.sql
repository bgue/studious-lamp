CREATE TABLE IF NOT EXISTS cur_qr_scan_code (
  id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  code_hash TEXT COLLATE "C" NOT NULL,
  target_id TEXT COLLATE "C" NOT NULL,
  target_type TEXT COLLATE "C" NOT NULL,
  label_text TEXT COLLATE "C",
  size TEXT COLLATE "C" NOT NULL DEFAULT 'tag',
  issued_by TEXT COLLATE "C" NOT NULL,
  issued_at TIMESTAMPTZ NOT NULL,
  expires_on DATE,
  revoked_at TIMESTAMPTZ,
  revoked_by TEXT COLLATE "C",
  revoke_reason TEXT COLLATE "C",
  replaced_by_id TEXT COLLATE "C",
  last_seq BIGINT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_qr_scan_code_code_hash ON cur_qr_scan_code (code_hash);

CREATE INDEX IF NOT EXISTS ix_cur_qr_scan_code_target ON cur_qr_scan_code (target_id);
