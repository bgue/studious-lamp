CREATE TABLE IF NOT EXISTS cur_enrichment_value (
  value_id TEXT COLLATE "C" PRIMARY KEY,
  scope TEXT COLLATE "C" NOT NULL,
  target_json JSONB NOT NULL DEFAULT '{}',
  target_id TEXT COLLATE "C" NOT NULL,
  property_path TEXT COLLATE "C" NOT NULL,
  value_json JSONB,
  enricher TEXT COLLATE "C" NOT NULL,
  enricher_version TEXT COLLATE "C" NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  inputs_json JSONB NOT NULL DEFAULT '{}',
  model_ref TEXT COLLATE "C",
  produced_at TEXT COLLATE "C" NOT NULL,
  acceptance_state TEXT COLLATE "C" NOT NULL,
  decided_by TEXT COLLATE "C",
  decided_at TIMESTAMPTZ,
  reason TEXT COLLATE "C",
  seq BIGINT NOT NULL,
  version BIGINT NOT NULL,
  last_seq BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_enrichment_value_scope ON cur_enrichment_value (scope);

CREATE INDEX IF NOT EXISTS ix_cur_enrichment_value_queue ON cur_enrichment_value (acceptance_state, seq);

CREATE INDEX IF NOT EXISTS ix_cur_enrichment_value_target ON cur_enrichment_value (target_id, property_path);
