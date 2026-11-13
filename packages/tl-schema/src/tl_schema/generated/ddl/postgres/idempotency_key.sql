CREATE TABLE IF NOT EXISTS idempotency_key (
  actor TEXT COLLATE "C" NOT NULL,
  idem_key TEXT COLLATE "C" NOT NULL,
  command TEXT COLLATE "C" NOT NULL,
  body_hash TEXT COLLATE "C" NOT NULL,
  result_json TEXT COLLATE "C",
  created_at TEXT COLLATE "C" NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_idempotency_key_actor_key ON idempotency_key (actor, idem_key);
