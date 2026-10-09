# P0-I1-T11 — Query helpers

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I1-T08
Branch: `p0/i1-t11-query-helpers`

## Goal
Two read functions over `cur_core_record` that return plain envelope dictionaries: `get_record(uow, scope, key)` and
`list_records(uow, scope, ...)`. The CLI, and later the TUI and API, use them instead of writing SQL.

## Brief references (pasted)
> Every entity type ... has a materialized current-state table. ... what every client, report, API query, and MCP tool reads by default. (§5.4)
> Common record envelope: `id`, `key`, `type`, `scope`, `title`, `description`, `status`, `psets{}`, ... `created_*`, `updated_*`, `version`. (§6.2)

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call.
- pyright strict applies to `tl_core` source. Annotate everything; no ignores. Bound parameters only.

## Interfaces (verbatim)
```python
# tl_core/uow.py (merged): UnitOfWork.conn() -> sqlalchemy.Connection
# tl_core/services/queries.py (create)
def get_record(uow: UnitOfWork, scope: str, key: str) -> dict[str, Any] | None: ...
def list_records(
    uow: UnitOfWork, scope: str, *, status: str | None = None, include_voided: bool = False
) -> list[dict[str, Any]]: ...
```
Envelope dict (exactly these keys): `id, key, type, scope, title, description, status, psets, voided, version, last_seq, effective_schema_hash, conformance, created_at, updated_at`.
`psets` is the parsed JSON object (from the `psets_json` column, which is not a key); `voided` is a Python `bool`; timestamps stay as the stored ISO strings.

Rules: `get_record` returns `None` when no row has that `(scope, key)`; it returns voided records too. `list_records` returns rows of the scope ordered by `created_at, id`;
voided rows are left out unless `include_voided=True`; `status` filters on equality when given.

Table columns: see `packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_core_record.sql`.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/uow.py`
- `packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_core_record.sql`
- `packages/tl-adapters/src/tl_adapters/sqlite/uow.py` (only `open_uow` and `create_schema`, for the tests)

## Allowed paths
- `packages/tl-core/src/tl_core/services/queries.py` (create; `services/__init__.py` already exists)
- `tests/services/test_record_queries.py` (create)

## Acceptance
```
just check
uv run pytest tests/services/test_record_queries.py -q
```

## Tests to add
`tests/services/test_record_queries.py`. Create `db = tmp_path / "tl.db"` with `create_schema(db)`; seed rows by appending real events through
`with open_uow(db) as uow: uow.append(stream_id=..., stream_type="core.Record", scope=..., expected_version=0, events=[NewEvent(event_type="Record.Created", payload={...})], actor="user:t", source="test", correlation_id="c")`
(and `Record.Voided` / `Record.Updated` events with `expected_version=1` to void or change status... status is only changeable through a `Record.Updated` with `{"changes": {"status": [None, "open"]}}`). Query with `open_uow(db, readonly=True)`.
- `get_record` returns the envelope dict with exactly the keys above, `psets` parsed (`{"a": 1}`), `voided` is `False`, `version == 1`; unknown key and a key in another scope return `None`.
- A voided record is still returned by `get_record` with `voided is True`.
- `list_records` returns only the scope's rows, ordered by creation; hides voided unless `include_voided=True`; `status="open"` returns only rows with that status.
- Both functions work on an empty table (`None`, `[]`).

## Report requirements
Standard report. List the test names.

## Escalation triggers
- Stop if the table columns differ from the envelope key list.

## Blocked

## Decision
