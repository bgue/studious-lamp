# P0-I1-T08 — `core.Record` projector

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I1-T04b, P0-I1-T05, P0-I1-T07 (projector contracts)
Branch: `p0/i1-t08-record-projector`

## Goal
`RecordProjector` turns the four record events (`Record.Created`, `Record.Updated`, `Record.Voided`, `Record.Corrected`) into
rows of `cur_core_record`, using the generated DDL. It is registered in `default_registry()`. Rows are never deleted; a void sets a flag.

## Brief references (pasted)
> Every entity type in the effective schema has a materialized current-state table. ... Updated in the same transaction as the events that change them (inline projector). ... Deterministic and rebuildable from the ledger. (§5.4)
> Corrections are explicit events (`*.Corrected`, `*.Voided`) with a mandatory reason. Voided records remain visible in audit views. (§5.2)

Event catalog (`docs/build-spec/03-repo-and-toolchain.md` §8):

| Event type | Payload |
|---|---|
| `Record.Created` | `record_type, key, title, description, psets{}` |
| `Record.Updated` | `changes{field: [old, new]}` |
| `Record.Voided` | `reason` |
| `Record.Corrected` | `changes{}, reason` (same `changes` shape as `Record.Updated`) |

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call.
- pyright runs in strict mode on `tl_core` source: annotate everything and add no ignores.
- A projector must be deterministic: no clock, no generated ids. Use only the event's own fields (`event.recorded_at`, `event.seq`, ...).

## Interfaces (verbatim)
Projector contract (`packages/tl-core/src/tl_core/projection/types.py`, do not change):
```python
class Projector(Protocol):
    name: str
    handles: frozenset[str]
    def ddl(self, dialect: str) -> list[str]: ...
    def apply(self, conn: Connection, event: Event) -> None: ...
    def reset(self, conn: Connection) -> None: ...
```
DDL loader (`packages/tl-schema/src/tl_schema/ddl_loader.py`): `statements(table: str, dialect: Dialect) -> list[str]` where
`Dialect = Literal["sqlite", "postgres"]` (from `tl_schema.generators.ddl_types`).
Helpers: `from tl_core.ledger import Event, canonical_json, iso_utc`.

Table `cur_core_record` (generated; read `packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_core_record.sql`):
columns `id, key, type, scope, title, description, status, psets_json, voided, version, last_seq, effective_schema_hash, conformance, created_at, updated_at`;
unique index on `(scope, key)`.

### `packages/tl-core/src/tl_core/projection/record.py` (create)
```python
class RecordProjector:
    name = "core_record"
    handles = frozenset({"Record.Created", "Record.Updated", "Record.Voided", "Record.Corrected"})
    def ddl(self, dialect: str) -> list[str]: ...
    def apply(self, conn: Connection, event: Event) -> None: ...
    def reset(self, conn: Connection) -> None: ...
```
Behaviour:
- `ddl(dialect)`: for `"sqlite"` or `"postgres"` return `statements("cur_core_record", dialect)`; any other value raises `ValueError(f"unsupported dialect: {dialect}")`.
- `reset(conn)`: `DELETE FROM cur_core_record`.
- `apply` for `Record.Created`: insert one row. `id = event.stream_id`; `key = payload.get("key")`; `type = payload["record_type"]`; `scope = event.scope`;
  `title = payload["title"]`; `description = payload.get("description")`; `status = NULL`; `psets_json = canonical_json(payload.get("psets") or {})`;
  `voided = False` (bind a Python `bool`); `version = event.stream_version`; `last_seq = event.seq`; `effective_schema_hash = NULL`; `conformance = "ok"`;
  `created_at = updated_at = iso_utc(event.recorded_at)`.
- `apply` for `Record.Updated` and `Record.Corrected`: `changes = payload["changes"]` maps a field name to `[old, new]`. Set each field to its `new` value. Allowed fields:
  `title`, `description`, `status`, `key`, `psets` (stored in `psets_json` as `canonical_json(new)`). Any other field raises `ValueError(f"unsupported field in changes: {field}")`.
  Also set `version = event.stream_version`, `last_seq = event.seq`, `updated_at = iso_utc(event.recorded_at)`.
- `apply` for `Record.Voided`: set `voided = True`, plus `version`, `last_seq`, `updated_at` as above. The row is never deleted.
- For every event except `Created`, if the UPDATE changed no row raise `LookupError(f"no cur_core_record row for stream {event.stream_id}")` (check `result.rowcount`).
- Use `sqlalchemy.text` with bound parameters only (never format values into SQL). Build the `SET` clause from a fixed whitelist of column names, never from event data.
- Any other event type raises `ValueError`.

### `packages/tl-core/src/tl_core/projection/defaults.py` (edit; replace the whole file with this)
```python
"""The projectors every ledger gets by default."""

from __future__ import annotations

from tl_core.projection.record import RecordProjector
from tl_core.projection.registry import InMemoryRegistry


def default_registry() -> InMemoryRegistry:
    """A fresh registry holding the built-in projectors. Later tickets register theirs here."""
    registry = InMemoryRegistry()
    registry.register(RecordProjector())
    return registry
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/projection/types.py`
- `packages/tl-core/src/tl_core/projection/defaults.py`
- `packages/tl-core/src/tl_core/ledger/types.py`
- `packages/tl-schema/src/tl_schema/ddl_loader.py`
- `packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_core_record.sql`

## Allowed paths
- `packages/tl-core/src/tl_core/projection/record.py` (create)
- `packages/tl-core/src/tl_core/projection/defaults.py` (replace)
- `packages/tl-core/tests/test_record_projector.py` (create)

## Acceptance
```
just check
uv run pytest packages/tl-core/tests/test_record_projector.py -q
```
Expected: all pass; `just check` shows pyright `0 errors`.

## Tests to add
`packages/tl-core/tests/test_record_projector.py`, using `sqlalchemy.create_engine("sqlite://", poolclass=StaticPool)` (an in-memory database shared by one connection), `engine.begin()` for each step, and hand-built `Event` objects (a small helper with a counter for `seq`, `stream_version`, fixed `recorded_at` values that differ per event):
- `ddl("sqlite")` creates the table; running the statements twice is harmless; `ddl("postgres")` returns statements whose text contains `JSONB`; `ddl("mysql")` raises `ValueError`.
- Created: every column of the stored row equals the specified value (check `psets_json` equals `{"a":1,"b":2}` for input psets `{"b": 2, "a": 1}`, `voided` is 0, `conformance` is `ok`, `status` is NULL, `version` 1, `last_seq` equals the event `seq`, `created_at == updated_at`).
- Updated: title and description change; `psets` change stores canonical JSON; `version`, `last_seq`, `updated_at` advance; `created_at` is unchanged.
- Corrected applies its `changes` the same way as Updated.
- Voided: `voided` becomes 1, the row still exists, and a later Updated still applies.
- An Updated for an unknown stream raises `LookupError`; a `changes` field `bogus` raises `ValueError`; an unsupported event type raises `ValueError`.
- Creating a second record with the same `(scope, key)` raises `sqlalchemy.exc.IntegrityError`; the same key in another scope succeeds.
- `reset` empties the table; replaying the same event list after `reset` gives rows identical to the first run (compare all columns).
- `default_registry().for_event("Record.Created")` contains a projector named `core_record`.

## Report requirements
Standard report. List the test names.

## Escalation triggers
- Stop if `cur_core_record` columns differ from the list above.
- Stop if pyright strict rejects code that follows this ticket; do not add ignores.

## Blocked

## Decision
