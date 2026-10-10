"""DDL for the Postgres ``events`` table, its indexes, and the triggers that keep it append-only.

``seq`` is a plain ``BIGINT`` primary key, assigned by the ledger as ``MAX(seq) + 1`` while it holds
the ledger lock. An identity column would burn a value on every rollback; this way ``seq`` is
gap-free and a rolled-back append leaves no trace, exactly as on SQLite. A writer that bypassed the
lock would collide on the primary key instead of silently reordering events.

``events.payload`` is TEXT, not JSONB, on purpose: the hash chain covers the canonical JSON text,
and JSONB would re-render numbers (``1e22`` becomes ``10000000000000000000000``), so a stored event
could no longer be re-hashed. Add a generated JSONB column when SQL-side payload queries need one.
"""

from __future__ import annotations

EVENTS_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS events (
      seq            BIGINT PRIMARY KEY,
      event_id       TEXT NOT NULL UNIQUE,
      stream_id      TEXT NOT NULL,
      stream_type    TEXT NOT NULL,
      stream_version BIGINT NOT NULL,
      event_type     TEXT NOT NULL,
      schema_version INTEGER NOT NULL,
      scope          TEXT NOT NULL,
      payload        TEXT NOT NULL,
      actor          TEXT NOT NULL,
      recorded_at    TIMESTAMPTZ NOT NULL,
      effective_at   TIMESTAMPTZ NOT NULL,
      correlation_id TEXT NOT NULL,
      causation_id   TEXT,
      source         TEXT NOT NULL,
      prev_hash      TEXT,
      hash           TEXT NOT NULL,
      UNIQUE (stream_id, stream_version)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_events_scope_seq ON events (scope, seq)",
    """
    CREATE OR REPLACE FUNCTION tl_events_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'events are append-only' USING ERRCODE = 'integrity_constraint_violation';
    END
    $$
    """,
    """
    CREATE OR REPLACE TRIGGER trg_events_no_update_delete
    BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION tl_events_append_only()
    """,
    """
    CREATE OR REPLACE TRIGGER trg_events_no_truncate
    BEFORE TRUNCATE ON events
    FOR EACH STATEMENT EXECUTE FUNCTION tl_events_append_only()
    """,
)
