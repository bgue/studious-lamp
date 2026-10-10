# P0-I4-T46 — HTTP client: records, queries and commands

Status: ready
Tier: haiku
Labels: api
Depends on: — (the client base and the routes of T40 are on the base branch)
Branch: `p0/i4c-t46-client-records`

## Goal
`ApiClient` (`tl_api.client`) offers the record half of the `ClientInterface`: `list_records`, `get_record`, `get_record_by_id`, `history`, `create_record`, `update_record`, `set_pset_values`, `edit_record`, plus the new `query_records` and `count_records` (orchestrator decision O3), over HTTP. `packages/tl-api/src/tl_api/client/records.py` has the class `RecordsApi` and the helper `format_order_by` with final signatures; the bodies raise `NotImplementedError`. Implementing them is the work. A provided test file (11 tests) must pass.

## Brief references (pasted)
> **4** The TUI must work in both embedded and remote modes through a single client interface, so the same screens run against a laptop SQLite file or a production server.
> **O3** `ClientInterface` gains `query_records(scope, q, *, limit, offset, order_by) -> list[dict]` and `count_records(scope, q) -> int`. The server parses `q`; a syntax error raises `QuerySyntaxError` carrying `position`.
> **11.1** Commands are `POST /commands/{CommandName}`; the actor is the token's, never the body's.

### Specification (the provided tests check it)
Calls go through the base helpers; error mapping (`QuerySyntaxError`, `DuplicateKeyError`, `ConcurrencyError` ...) is already done by `_send`. Always put an id into a path with `quote(...)`.
- **`format_order_by(order_by)`**: `None` or empty gives `None`; else `",".join(f"{column}:{direction}" for column, direction in order_by)`.
- **`list_records`**: `self._get_json("/records", {...})` with `scope`, `record_type`, `status`, `include_voided`, `limit`, `offset` and `order_by=format_order_by(order_by)` (None values are dropped by the base). Return the JSON list unchanged (a list of envelope dicts).
- **`query_records(scope, q, *, limit, offset, order_by)`**: the same endpoint with `scope`, `q`, `limit`, `offset`, `order_by`.
- **`count_records(scope, q)`**: `int(self._get_json("/records/count", {"scope": scope, "q": q})["count"])`.
- **`get_record(scope, key)`**: `self._get_json("/records/lookup", {"scope": scope, "key": key})`; catch `RecordNotFoundError` and return `None`.
- **`get_record_by_id(record_id)`**: `self._get_json(f"/records/{quote(record_id)}")`; `RecordNotFoundError` gives `None`.
- **`history(record_id)`**: `self._models(Event, self._get_json(f"/records/{quote(record_id)}/history"))`; `RecordNotFoundError` gives `[]`.
- **`create_record`, `update_record`, `set_pset_values`, `edit_record`**: `return self._command("CreateRecord", cmd)` / `"UpdateRecord"` / `"SetPsetValues"` / `"EditRecord"`.
- Imports to add: `from tl_core.services.errors import RecordNotFoundError` and `quote` from `tl_api.client.base` (extend the existing import).

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt`; you copy them into the test tree and must not edit the copy. The supervisor formatted them already; `diff` the copy against the original in the last acceptance step.
- The test harnesses (`packages/tl-api/tests/conftest.py`, `harness.py`; `packages/tl-mcp/tests/conftest.py`, `mcp_harness.py`) run a real app or server over a real SQLite file. Tests import them with `from harness import ...` / `from mcp_harness import ...`. Do not edit them and do not add `__init__.py` to a test directory.
- `just check` includes an OpenAPI drift check. You change no route, so it must stay green; never regenerate or edit `docs/reference/openapi.json`.
- ruff limits lines to 100 columns; run `uv run ruff format packages` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/<ticket-id>.md`); it is inside your Allowed paths.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-api/src/tl_api/client/base.py (final) - the class every group below extends
class ApiClientBase:
    _http: httpx2.Client                       # one connection pool; self._auth holds the Authorization header
    def _send(self, method: str, path: str, *, params=None, json=None, content=None, headers=None) -> httpx2.Response
        # None params are dropped; status >= 400 raises the mapped exception (ServiceError subclasses, ConcurrencyError, ApiError ...)
    def _get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any
    def _post_json(self, path: str, body: Any, params: Mapping[str, Any] | None = None) -> Any
    @staticmethod def _model(model: type[M], data: Any) -> M          # model.model_validate(data)
    @staticmethod def _models(model: type[M], data: Any) -> list[M]    # a list of validated models
    def _command(self, name: str, command: Command) -> CommandResult  # POST /commands/<name>, actor left out, source kept
    @staticmethod def error_from(response: httpx2.Response) -> Exception
def quote(segment: str) -> str    # urllib.parse.quote(segment, safe=""): use it for every id put into a path
# packages/tl-api/src/tl_api/client/records.py (the stub; keep every name and signature)
OrderBy = list[tuple[str, Literal["asc", "desc"]]]
def format_order_by(order_by: OrderBy | None) -> str | None
class RecordsApi(ApiClientBase):
    def list_records(self, scope, *, record_type=None, status=None, include_voided=False, limit=500, offset=0, order_by=None) -> list[dict[str, Any]]
    def query_records(self, scope, q, *, limit=500, offset=0, order_by=None) -> list[dict[str, Any]]
    def count_records(self, scope: str, q: str) -> int
    def get_record(self, scope, key) -> dict | None;  def get_record_by_id(self, record_id) -> dict | None;  def history(self, record_id) -> list[Event]
    def create_record(self, cmd: CreateRecord) -> CommandResult  # and update_record(UpdateRecord), set_pset_values(SetPsetValues), edit_record(EditRecord)
# HTTP (final, tested server side): GET /records, /records/count, /records/lookup, /records/{id}, /records/{id}/history; POST /commands/{Name}
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-api/src/tl_api/client/records.py` (the stub)
- `packages/tl-api/src/tl_api/client/base.py`
- `packages/tl-api/tests/harness.py`
- `docs/tickets/P0-I4/provided/test_client_records.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/client/records.py` (edit)
- `packages/tl-api/tests/test_client_records.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T46.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_client_records.py.txt packages/tl-api/tests/test_client_records.py`
2. Implement the helper and the methods; delete the `STUB (P0-I4-T46)` paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-api/tests/test_client_records.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_client_records.py.txt packages/tl-api/tests/test_client_records.py
```
Expected: 11 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file(s).

## Report requirements
Standard report plus the decisive lines of the acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification, or if you think a signature must change.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
