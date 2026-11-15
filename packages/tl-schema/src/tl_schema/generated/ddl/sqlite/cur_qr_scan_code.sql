CREATE TABLE IF NOT EXISTS cur_qr_scan_code (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  target_id TEXT NOT NULL,
  target_type TEXT NOT NULL,
  label_text TEXT,
  size TEXT NOT NULL DEFAULT 'tag',
  issued_by TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  expires_on TEXT,
  revoked_at TEXT,
  revoked_by TEXT,
  revoke_reason TEXT,
  replaced_by_id TEXT,
  last_seq INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_qr_scan_code_code_hash ON cur_qr_scan_code (code_hash);

CREATE INDEX IF NOT EXISTS ix_cur_qr_scan_code_target ON cur_qr_scan_code (target_id);
