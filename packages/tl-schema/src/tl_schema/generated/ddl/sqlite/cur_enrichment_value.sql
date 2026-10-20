CREATE TABLE IF NOT EXISTS cur_enrichment_value (
  value_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  target_json TEXT NOT NULL DEFAULT '{}',
  target_id TEXT NOT NULL,
  property_path TEXT NOT NULL,
  value_json TEXT,
  enricher TEXT NOT NULL,
  enricher_version TEXT NOT NULL,
  confidence REAL NOT NULL,
  inputs_json TEXT NOT NULL DEFAULT '{}',
  model_ref TEXT,
  produced_at TEXT NOT NULL,
  acceptance_state TEXT NOT NULL,
  decided_by TEXT,
  decided_at TEXT,
  reason TEXT,
  seq INTEGER NOT NULL,
  version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_enrichment_value_scope ON cur_enrichment_value (scope);

CREATE INDEX IF NOT EXISTS ix_cur_enrichment_value_queue ON cur_enrichment_value (acceptance_state, seq);

CREATE INDEX IF NOT EXISTS ix_cur_enrichment_value_target ON cur_enrichment_value (target_id, property_path);
