CREATE TABLE IF NOT EXISTS idempotency_key (
  actor TEXT NOT NULL,
  idem_key TEXT NOT NULL,
  command TEXT NOT NULL,
  body_hash TEXT NOT NULL,
  result_json TEXT,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_idempotency_key_actor_key ON idempotency_key (actor, idem_key);
