# P0-I8-T21 — API routes for extension types and their bodies

Status: ready
Tier: haiku
Labels: api
Depends on: S23 (body store), S24 (`type_detail`, `ApiContext.objects`, error rows), merged on `p0/i8b`
Branch: `p0/i8b-t21-api-types`

## Goal
The REST API serves extension types (brief 31.3, "generic API"): `GET /types` and `GET /types/{type_ref}` read the registry, `POST /types/{type_name}/records` creates an
instance of a type (psets for a managed type, a body for an object-backed one, in one unit of work), `GET /records/{record_id}/body` returns the verified body of an
object-backed record and `PUT /records/{record_id}/body` stores a new one. Reading instances needs no new route: `GET /records?record_type=co.acme.LiftPlan` and the query
language already do it. Every rule is in `tl_core.extypes`; the routes parse, call one service function and map nothing by hand (the error table already maps every error).

## Brief references (pasted)
> §31.2 **Write paths (object-backed):** through Throughline (TUI/API/MCP) the body is validated, stored as an object, then a metadata event referencing its hash is appended.
> Updates are new document versions (new hash). Old versions are immutable, and the ledger keeps the version chain.
>
> §31.4 Bodies are never trusted without validation. Hashes are verified on read, and mismatches are quarantined. **Index fields are the query contract.** Other body fields are visible
> in the record view but not filterable server-side.
>
> Decisions for this ticket: registering a package is an operator action on files (`tl types sync`), so the registry is read-only over HTTP. A write is a record change: an `agent:`
> token gets 403 `agent_must_propose` (the `Writer` dependency does this). Without an object store (`ctx.objects is None`) the body routes answer 503 `unavailable`.
> Error codes already in the table: `type_not_found` 404, `body_required` 422, `body_not_allowed` 422, `body_invalid` 422 (with `issues`), `body_not_found` 404,
> `body_quarantined` 403, `body_hash_mismatch` 502, `concurrency_conflict` 409, `record_not_found` 404, `unsupported_record_type` 422.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_core/extypes/registry.py
def list_types(conn, *, status: TypeStatus | None = None) -> list[TypeView]: ...
# tl_core/extypes/service.py
def type_detail(uow, type_ref: str) -> TypeDetail: ...        # UnknownTypeError when unknown
# tl_core/extypes/body.py
def create_extension_record(uow, store, cmd: CreateRecord, body: dict[str, Any]) -> CommandResult: ...
    # object-backed types; refuses a managed type (BodyNotAllowedError) and cmd.psets
def store_body(uow, store, *, stream_id: str, body: dict[str, Any], actor: str, source: str,
               expected_version: int | None = None) -> BodyPointer: ...
def body_pointer(conn, stream_id: str) -> BodyPointer | None: ...
def read_body(factory, store, *, stream_id: str) -> dict[str, Any]: ...
    # factory(readonly=...) yields a unit of work; on a hash mismatch it records the quarantine, then raises
# tl_core/extypes/service.py
class TypeSummary(BaseModel): ...; class BodyView(BaseModel): record_id: str; pointer: BodyPointer; body: dict[str, Any]
def summarise(view: TypeView) -> TypeSummary: ...      # given: use it
# tl_core/services/records.py, queries.py
def handle_create_record(uow, cmd: CreateRecord) -> CommandResult: ...
def get_record_by_id(uow, record_id: str) -> dict[str, Any] | None: ...   # has "scope" and "version"
# tl_core/services/commands.py
class CreateRecord(Command):  # actor, source, scope, record_type, title, description, key, psets, numbering
class CommandResult(BaseModel): stream_id: str; key: str | None; version: int; events: list[Event]
# tl_api/context.py
class ApiContext:  backend: Backend; objects: ObjectStore | None; ...     # ctx.backend(readonly) yields a unit of work
# tl_api/errors.py
class ApiError(Exception): ApiError(status: int, error: str, message: str)
```
The stub `packages/tl-api/src/tl_api/routes/extypes.py` has the models, the router, the dependencies, every route decorator and signature, and a docstring on each unfinished function
that says what to call. Replace each `raise NotImplementedError("STUB (P0-I8-T21)")`. The router is already included in `create_app`; do not touch `app.py`.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/extypes.py` (the stub)
- `packages/tl-api/src/tl_api/routes/proposals.py` (a finished router of the same shape)
- `docs/tickets/P0-I8/provided/b-test_api_extypes.py.txt` (the test to make pass)
- `packages/tl-api/tests/harness.py` (read only; it builds the app the test uses)
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/extypes.py` (replace the stub bodies)
- `packages/tl-api/tests/test_api_extypes.py` (create: copy of the provided file, unchanged)
- `docs/reports/P0-I8/P0-I8-T21.md` (create: your report; commit it)

## Steps
1. `uv sync --all-packages`. Run every command from the repository root.
2. `cp docs/tickets/P0-I8/provided/b-test_api_extypes.py.txt packages/tl-api/tests/test_api_extypes.py`. Do not edit it.
3. Fill in the stub bodies. The unit of work is `ctx.backend(True)` for reads and `ctx.backend(False)` for writes, used as a context manager.
4. `docs/reference/openapi.json` is already current (the stub keeps every decorator, parameter and docstring that reaches it). `uv run python -m tl_api.openapi --check` must pass and you must not change that file. If the check fails, a signature or docstring of the stub changed: undo that.

## Acceptance
```
just check
uv run pytest packages/tl-api/tests/test_api_extypes.py -q
uv run pytest packages/tl-api -q
```
Expected: `just check` clean except the known failure below; 20 passed in `test_api_extypes.py`; the rest of `packages/tl-api` still passes (`test_openapi.py` included).
Known and not yours: `uv run pytest packages/tl-schema` fails `test_every_event_type_the_code_names_is_in_the_catalog` (another workstream's event types). Do not run or fix it.

## Tests to add
- `packages/tl-api/tests/test_api_extypes.py`: the provided file. It covers the registry reads, a managed and an object-backed create, the wrong kind of content, an invalid body (issues
  listed, nothing written), the body read and replace (ETag, stale version, wrong scope, unknown record), a damaged object (502, then 403, healed by storing again), no object store
  (503) and the agent rule.

## Report requirements
Standard report. Paste the output of the three acceptance commands and of `uv run python -m tl_api.openapi --check`.

## Rules to remember (from the project's learnings)
- The committed OpenAPI document is drift-checked by `just check`: keep every decorator, parameter, annotation and docstring of the stub exactly as it is, because they reach the document.
- A route does not catch and re-raise: the error table maps `ServiceError`s. The one error raised by hand is `ApiError(503, "unavailable", ...)` for a missing object store.
- Ruff's line limit is 100 columns, including docstrings. Write files with the Write or Edit tool. Never use `pkill -f`. Commit as `P0-I8-T21: <summary>`, report included.

## Escalation triggers
- Stop and report *Blocked* if a docstring and the provided test disagree, if a function under Interfaces is missing, if `--check` fails after you restored the stub's signatures, or if you would
  have to touch a file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
