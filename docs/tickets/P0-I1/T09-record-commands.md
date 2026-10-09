# P0-I1-T09 — Record command handlers

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I1-T07, P0-I1-T08
Branch: `p0/i1-t09-record-commands`

## Goal
Command models `CreateRecord`, `UpdateRecord`, `VoidRecord` and handlers `handle_create_record`, `handle_update_record`,
`handle_void_record` that validate a command, read the current row if needed, and emit exactly the ledger events through a
`UnitOfWork`. Handlers contain the only business rules for records in this increment; the CLI will call them and add nothing.

## Brief references (pasted)
> Every write is a command validated by the service layer, which emits one or more events in a single transaction. (§5.1)
> Corrections are explicit events (`*.Corrected`, `*.Voided`) with a mandatory reason. Voided records remain visible in audit views. (§5.2)
> Keep all business logic out of the TUI; screens consume the same query/command contracts the web client will. (§16)

Event catalog (`docs/build-spec/03-repo-and-toolchain.md` §8): `Record.Created {record_type, key, title, description, psets}`;
`Record.Updated {changes: {field: [old, new]}}`; `Record.Voided {reason}`.

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call.
- pyright strict applies to `tl_core` source. Annotate everything; no ignores.
- Numbering does not exist yet: `CreateRecord.key` is required in this increment.

## Interfaces (verbatim)
```python
# tl_core/uow.py (merged)
class UnitOfWork(Protocol):
    ledger: Ledger
    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def append(self, **kwargs: Any) -> AppendResult: ...   # keywords: stream_id, stream_type, scope, expected_version, events, actor, source, correlation_id, causation_id
    def conn(self) -> Connection: ...                      # SQLAlchemy Connection; use sqlalchemy.text with bound parameters

# tl_core/ledger (merged): NewEvent(event_type, payload, schema_version=1, effective_at=None), Event, AppendResult(events, new_version, last_seq), ConcurrencyError
# tl_core/util.py (merged): new_ulid() -> str
```
`handle_*` run inside an already-entered unit of work (`with open_uow(path) as uow:` supplies one); they never commit.

### `packages/tl-core/src/tl_core/services/errors.py` (create, exact names)
```python
class ServiceError(Exception): """Base class for expected, user-correctable command failures."""
class KeyRequiredError(ServiceError): ...          # CreateRecord without a key
class DuplicateKeyError(ServiceError): ...         # (scope, key) already exists, voided or not
class UnsupportedRecordTypeError(ServiceError): ...  # record_type other than "core.Record"
class RecordNotFoundError(ServiceError): ...       # stream_id unknown, or it belongs to another scope
class RecordVoidedError(ServiceError): ...         # update of a voided record
class AlreadyVoidedError(ServiceError): ...        # void of a voided record
class NoChangesError(ServiceError): ...            # update where nothing differs
class UnsupportedFieldError(ServiceError): ...     # update of a field outside title/description/psets
```
Each takes a human-readable message.

### `packages/tl-core/src/tl_core/services/commands.py` (create)
```python
class Command(BaseModel):
    actor: str
    source: str
    scope: str                      # must match ^(company|project:[A-Za-z0-9_.-]+)$ (pydantic field_validator -> ValidationError)
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None   # accepted and ignored in this increment (idempotency is later work)

class CreateRecord(Command):
    record_type: str                # Phase 0: only "core.Record"
    title: str                      # min_length 1
    description: str | None = None
    key: str | None = None
    psets: dict[str, Any] = {}

class UpdateRecord(Command):
    stream_id: str
    expected_version: int
    changes: dict[str, Any]         # new values by field name

class VoidRecord(Command):
    stream_id: str
    expected_version: int
    reason: str                     # non-blank after strip (field_validator -> ValidationError)

class CommandResult(BaseModel):
    stream_id: str
    key: str | None
    version: int
    events: list[Event]
```

### `packages/tl-core/src/tl_core/services/records.py` (create)
```python
def handle_create_record(uow: UnitOfWork, cmd: CreateRecord) -> CommandResult: ...
def handle_update_record(uow: UnitOfWork, cmd: UpdateRecord) -> CommandResult: ...
def handle_void_record(uow: UnitOfWork, cmd: VoidRecord) -> CommandResult: ...
```
Rules, in order, for each handler (raise the named error and write nothing on failure):
- **create:** `record_type != "core.Record"` raises `UnsupportedRecordTypeError`; `key is None` raises `KeyRequiredError`; if
  `SELECT 1 FROM cur_core_record WHERE scope = :scope AND key = :key` returns a row raise `DuplicateKeyError`. Then `stream_id = new_ulid()`,
  `correlation_id = cmd.correlation_id or new_ulid()`, and one `uow.append(stream_id=..., stream_type=cmd.record_type, scope=cmd.scope, expected_version=0,
  events=[NewEvent(event_type="Record.Created", payload={"record_type", "key", "title", "description", "psets"})], actor=cmd.actor, source=cmd.source,
  correlation_id=correlation_id, causation_id=cmd.causation_id)`. Result: `CommandResult(stream_id, key=cmd.key, version=result.new_version, events=result.events)`.
- **update:** load the row (`SELECT scope, key, title, description, psets_json, voided FROM cur_core_record WHERE id = :id`); missing or `scope != cmd.scope` raises
  `RecordNotFoundError`; `voided` raises `RecordVoidedError`; a changed field not in `{"title", "description", "psets"}` raises `UnsupportedFieldError`
  (check the fields before comparing). Build `changes = {field: [old, new]}` only for fields whose new value differs from the stored one (`psets` compared as dicts; old
  `psets` is `json.loads(psets_json)`); if empty raise `NoChangesError`. Append one `Record.Updated` with `expected_version=cmd.expected_version`
  (a stale version surfaces as the ledger's `ConcurrencyError`; do not catch it). Result key is the stored key.
- **void:** same load and scope check; already voided raises `AlreadyVoidedError`; append one `Record.Voided` with payload `{"reason": cmd.reason}` and `expected_version=cmd.expected_version`.
- `stream_type` for update and void is `"core.Record"`.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/uow.py`
- `packages/tl-core/src/tl_core/ledger/types.py`
- `packages/tl-core/src/tl_core/projection/record.py`
- `packages/tl-adapters/src/tl_adapters/sqlite/uow.py` (only `open_uow` and `create_schema`, for the tests)

## Allowed paths
- `packages/tl-core/src/tl_core/services/errors.py`, `commands.py`, `records.py` (create; `services/__init__.py` already exists, leave it empty)
- `tests/services/test_record_commands.py` (create)

## Acceptance
```
just check
uv run pytest tests/services/test_record_commands.py -q
```
Expected: all pass.

## Tests to add
`tests/services/test_record_commands.py`. Fixture: `db = tmp_path / "tl.db"`, `create_schema(db)` from `tl_adapters.sqlite.uow`, and a helper `run(handler, cmd)` that does
`with open_uow(db) as uow: return handler(uow, cmd)`. Read results back with `open_uow(db, readonly=True)` and `text("SELECT ... FROM cur_core_record")`.
- create: one `Record.Created` event with the exact payload; row exists with title, key, version 1; result `key`, `version == 1`, `stream_id` is a 26-character string; passed
  `correlation_id` is stored on the event, absent one becomes a 26-character string; `actor`/`source` stored.
- create failures: no key (`KeyRequiredError`), same key in same scope (`DuplicateKeyError`, and the first record is unchanged), same key in another scope succeeds,
  `record_type="qc.Inspection"` (`UnsupportedRecordTypeError`), empty title and bad scope (`pydantic.ValidationError`).
- update: changing title and description emits `Record.Updated` with `{"title": [old, new], ...}` and the row shows the new values and version 2; an unchanged field is left out of `changes`;
  `psets` change works; no differences raises `NoChangesError`; `status` field raises `UnsupportedFieldError`; stale `expected_version` raises `tl_core.ledger.ConcurrencyError` and writes nothing;
  unknown stream and wrong-scope stream raise `RecordNotFoundError`; updating a voided record raises `RecordVoidedError`.
- void: emits `Record.Voided {"reason": ...}`, row has `voided = 1` and still exists, version 2; blank reason is a `ValidationError`; voiding twice raises `AlreadyVoidedError`.
- atomicity: a handler failure inside `with open_uow(db)` leaves the ledger and table unchanged (assert `head_seq` is unchanged after a `DuplicateKeyError`).

## Report requirements
Standard report. List the test names.

## Escalation triggers
- Stop if any interface above differs from the repo. Do not adapt it.
- Stop rather than implement numbering or idempotency: both are later increments.

## Blocked

## Decision
