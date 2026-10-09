# P0-I2-T10 — `Schema.EffectiveChanged` event and hot-reload hook

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I2-T03 (merged into the base of this branch)
Branch: `p0/i2a-t10-effective-changed-event`

## Goal
`tl_core/services/schema_events.py` records a `Schema.EffectiveChanged` ledger event when a scope's effective schema hash changes, and offers
a bus subscriber that reloads the packages and records changes whenever a `SchemaPackage.Published` event is seen. The module is a stub with
documented signatures; after this ticket the stub bodies work and a provided test file passes (8 tests).

## Brief references (pasted)
> **27.3** The effective schema is hot-reloaded. Clients receive a `Schema.EffectiveChanged` event and refresh forms and metadata without a restart. Records being edited keep validating against the schema they were opened with until saved, then are re-checked.
> **27.4** Publishing emits `SchemaPackage.Published` (feed card + webhooks) and makes the version available to adopt.
> **27.1** Every event records the `effective_schema_hash` it was validated against.
> Event catalog (build spec 03 section 8): `SchemaPackage.Published`, `Schema.EffectiveChanged` — payload `package, version, effective_schema_hash` (minimum; this ticket adds the fields below).

### Specification (the provided test checks it)
- `EVENT_TYPE`, `PUBLISHED_EVENT_TYPE`, `STREAM_TYPE`, `ACTOR`, `SOURCE` are already defined; use them.
- `schema_stream_id(scope)` returns `f"schema:{scope}"`.
- `record_effective_schema(uow, schema)`:
  1. `stream_id = schema_stream_id(schema.scope)`; `history = uow.ledger.read_stream(stream_id)`; `last = history[-1] if history else None`.
  2. If `last` exists and `last.payload["effective_schema_hash"] == schema.hash`, return `None` (nothing appended).
  3. Otherwise `uow.append(stream_id=stream_id, stream_type=STREAM_TYPE, scope=schema.scope, expected_version=last.stream_version if last else 0, events=[NewEvent(event_type=EVENT_TYPE, payload=...)], actor=ACTOR, source=SOURCE, correlation_id=new_ulid())` and return `result.events[0]`.
  4. Payload keys, exactly: `scope` (`schema.scope`), `effective_schema_hash` (`schema.hash`), `previous_hash` (the last recorded hash or `None`), `packages` (`[f"{p.name}@{p.version}" for p in schema.packages]`, already sorted by `EffectiveSchema`).
- `reload_and_record(uow, provider)`: call `provider.reload()`; then for each `scope` in `provider.scopes()` call `record_effective_schema(uow, provider.effective(scope))`; return the non-`None` events in that order.
- `schema_reload_subscriber(provider, open_uow)` returns a function `on_event(event)`: if `event.event_type != PUBLISHED_EVENT_TYPE` do nothing; otherwise `with open_uow() as uow: reload_and_record(uow, provider)`. (A write inside a bus callback is delivered after the callback returns; no extra handling is needed.)

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I2/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copied test.
- pyright is strict for `packages/tl-core/src`; `ruff` enforces 100 columns including docstrings. Remove the `STUB:` paragraph from the module docstring when you are done.
- A Protocol attribute that implementers narrow must be a read-only property (L-P0-I1-10); you do not change any Protocol here.
- `uv` prints "UV_NATIVE_TLS is deprecated" on every call; ignore it. If imports fail in a fresh worktree run `uv sync --all-packages`. Do not pipe `just check` into `tail`.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/services/schema_events.py (stub: keep names and signatures, replace the bodies)
EVENT_TYPE = "Schema.EffectiveChanged"; PUBLISHED_EVENT_TYPE = "SchemaPackage.Published"
STREAM_TYPE = "schema"; ACTOR = "svc:schema"; SOURCE = "schema-reload"
def schema_stream_id(scope: str) -> str: ...
def record_effective_schema(uow: UnitOfWork, schema: EffectiveSchema) -> Event | None: ...
def reload_and_record(uow: UnitOfWork, provider: ReloadableSchemaProvider) -> list[Event]: ...
def schema_reload_subscriber(provider: ReloadableSchemaProvider,
                             open_uow: Callable[[], AbstractContextManager[UnitOfWork]]) -> Callable[[Event], None]: ...
```
```python
# packages/tl-core/src/tl_core/schema_provider.py (read-only)
class ReloadableSchemaProvider(SchemaProvider, Protocol):
    def effective(self, scope: str) -> EffectiveSchema: ...
    def scopes(self) -> list[str]: ...          # "company" and every "project:<id>"
    def reload(self) -> list[SchemaChange]: ...
# tl_core.ledger: NewEvent(event_type, payload), Event (stream_version, payload, scope, ...)
# tl_core.util: new_ulid() -> str
# UnitOfWork: .ledger.read_stream(stream_id) -> list[Event]; .append(**kwargs) -> AppendResult(events, new_version, last_seq)
# EffectiveSchema: .scope, .hash, .packages: list[PackageRef(name, version)]
```
Imports to add: `NewEvent` from `tl_core.ledger`, `new_ulid` from `tl_core.util`.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/schema_events.py`
- `packages/tl-core/src/tl_core/schema_provider.py`
- `packages/tl-core/src/tl_core/uow.py`
- `docs/tickets/P0-I2/provided/test_schema_events.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/services/schema_events.py` (edit: implement the stub)
- `tests/services/test_schema_events.py` (create: `cp` of the provided file, byte for byte)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_schema_events.py.txt tests/services/test_schema_events.py`
2. Implement the four functions; remove the `STUB:` paragraph.
3. Run the acceptance commands.

## Acceptance
```
uv run pytest tests/services/test_schema_events.py -q
just check
just test
diff docs/tickets/P0-I2/provided/test_schema_events.py.txt tests/services/test_schema_events.py
```
Expected: 8 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands and the test count.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `schema_provider.py`, `uow.py` or the bus.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
