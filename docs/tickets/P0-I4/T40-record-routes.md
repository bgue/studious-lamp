# P0-I4-T40 — Record read routes

Status: ready
Tier: haiku
Labels: api
Depends on: — (the app, auth, error table and harness are on the base branch; WS-A's query language is merged)
Branch: `p0/i4c-t40-record-routes`

## Goal
`GET /records` (query language, paging, ordering), `GET /records/count`, `GET /records/lookup`, `GET /records/{record_id}` and
`GET /records/{record_id}/history` return real data. The module `packages/tl-api/src/tl_api/routes/records.py` exists with final
signatures, decorators and response models; the two helpers `parse_order_by` and `build_spec` and the five route bodies raise
`NotImplementedError`. Implementing those seven bodies is the work. A provided test file (14 tests) must pass.

## Brief references (pasted)
> **11.1** REST/JSON: resource-oriented; filtering with the same query language as the TUI; ETags = `stream_version`.
> **10.2 Filter bar**: structured query builder plus text query language, e.g. `status:open discipline:PIP psets.nde.method=RT due<+7d linked:NCR`.
> **O3 (orchestrator decision)**: the server parses the text (`tl_core.query.parse`). A `QuerySyntaxError` becomes HTTP 400 `{"error": "query_syntax", "message": ..., "position": n}`; the error table in `tl_api/errors.py` already does that, so you only let the exception propagate.

### Specification (the provided test checks it)
Routes call `tl_core` only, through `ctx.backend(readonly)` (a context manager that yields an entered unit of work). No SQL, no business rules.
- **`parse_order_by(text)`**: `None` or blank gives `[]`. Otherwise split on commas; for each item `column, _, direction = item.strip().partition(":")`; the direction (stripped, lower-cased) defaults to `"asc"`. An item with an empty column, or a direction other than `asc` or `desc`, raises `ApiError(422, "invalid_argument", f"order_by item {item!r} must be <column>[:asc|:desc]")`. Return `[(column.strip(), "asc" | "desc"), ...]`. Whether a column exists is not checked here (the query layer does).
- **`build_spec(scope, q, *, record_type, status, include_voided, limit, offset, order_by)`**: `where = parse(q) if q else None` (`parse` from `tl_core.query`; blank gives `None`). If `status` is not `None`, `condition = Compare("status", "=", status)` and `where = condition if where is None else And((where, condition))`. Return `QuerySpec(scope=scope, record_type=record_type, where=where, order_by=parse_order_by(order_by), limit=limit, offset=offset, include_voided=include_voided)`.
- **`list_records`**: `spec = build_spec(...)` with the route's parameters; `with ctx.backend(True) as uow: rows = run_query(uow, spec)`; wrap that `with` in `try/except ValueError as exc: raise ApiError(422, "invalid_argument", str(exc)) from exc` (an unknown order column raises `ValueError`). Return `[RecordOut(**row) for row in rows]`.
- **`count_records`**: `spec = build_spec(scope, q, record_type=..., status=..., include_voided=...)` (default limit and offset); `with ctx.backend(True) as uow: return CountOut(count=count_query(uow, spec))`.
- **`lookup_record`**: `with ctx.backend(True) as uow: row = queries.get_record(uow, scope, key)`. If `row is None`, `raise RecordNotFoundError(f"no record with key {key!r} in scope {scope!r}")`. Set `response.headers["ETag"] = f'"{row["version"]}"'`; return `RecordOut(**row)`.
- **`get_record`**: same with `queries.get_record_by_id(uow, record_id)`; message `f"no record {record_id!r}"`; same ETag.
- **`get_record_history`**: `events = queries.record_history(uow, record_id)` inside `with ctx.backend(True) as uow:`; if the list is empty `raise RecordNotFoundError(f"no record {record_id!r}")`; return `events`.
- Imports to add (the stub omits them so `just check` stays green): `from tl_core.query import And, Compare, Expr, QuerySpec, count_query, parse, run_query` (extend the existing `QuerySpec` import), `from tl_core.services import queries`, `from tl_core.services.errors import RecordNotFoundError`, `from tl_api.errors import ApiError`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt`; you copy them into the test tree and must not edit the copy. A `.py.txt` is outside `ruff format`, so the supervisor formatted it already; `diff` it against the original in the last acceptance step.
- The package `tl-api` has a test harness (`packages/tl-api/tests/conftest.py`, `harness.py`): a real app over a real SQLite file. Tests import it with `from harness import ...`. Do not edit it and do not add `__init__.py` to the test directory.
- `just check` includes an OpenAPI drift check (`uv run python -m tl_api.openapi --check`). The stub's signatures, decorators, parameters and response models are final and already in the committed document. If `just check` reports the document out of date, you changed a signature: put it back. Never regenerate or edit `docs/reference/openapi.json`.
- ruff limits lines to 100 columns; run `uv run ruff format packages/tl-api` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/<ticket-id>.md`); it is inside your Allowed paths.
- Route order matters: `/records/count` and `/records/lookup` are declared before `/records/{record_id}`. Keep the order.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/query/api.py (final)
@dataclass(frozen=True)
class QuerySpec:
    scope: str
    record_type: str | None = None
    where: Expr | None = None
    order_by: list[tuple[str, Literal["asc", "desc"]]] = ...
    limit: int | None = 500
    offset: int = 0
    include_voided: bool = False
def parse(text: str) -> Expr | None            # blank -> None; raises QuerySyntaxError
def run_query(uow: UnitOfWork, spec: QuerySpec) -> list[dict[str, Any]]    # ValueError: bad order_by column
def count_query(uow: UnitOfWork, spec: QuerySpec) -> int
# packages/tl-core/src/tl_core/query/ast.py (final)
@dataclass(frozen=True)
class Compare: path: str; op: CompareOp; value: Value      # Compare("status", "=", "Review")
@dataclass(frozen=True)
class And: items: tuple[Expr, ...]
# packages/tl-core/src/tl_core/services/queries.py (final)
def get_record(uow, scope: str, key: str) -> dict[str, Any] | None
def get_record_by_id(uow, record_id: str) -> dict[str, Any] | None
def record_history(uow, record_id: str) -> list[Event]       # [] when the record is unknown
# packages/tl-api (final)
class RecordOut(BaseModel): id, key, type, scope, title, description, status, psets, voided, version, last_seq, effective_schema_hash, conformance, created_at, updated_at
class CountOut(BaseModel): count: int
class ApiError(Exception): def __init__(self, status: int, error: str, message: str, body: dict | None = None)
ctx.backend(readonly: bool) -> AbstractContextManager[UnitOfWork]
```
The stub (`packages/tl-api/src/tl_api/routes/records.py`) is the other interface: keep every name, decorator, parameter and annotation.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-api/src/tl_api/routes/records.py` (the stub)
- `packages/tl-api/tests/harness.py` (what the tests call)
- `docs/tickets/P0-I4/provided/test_api_records.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/records.py` (edit)
- `packages/tl-api/tests/test_api_records.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T40.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_api_records.py.txt packages/tl-api/tests/test_api_records.py`
2. Implement the two helpers and the five routes; delete the `STUB (P0-I4-T40)` paragraph from the module docstring.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-api/tests/test_api_records.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_api_records.py.txt packages/tl-api/tests/test_api_records.py
```
Expected: 14 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification, or if you think a signature must change.
- Stop rather than change any other file (`app.py`, `errors.py`, `models.py`, `openapi.json` are not yours).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
