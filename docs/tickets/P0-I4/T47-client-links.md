# P0-I4-T47 — HTTP client: links, workflow, schema and reference

Status: ready
Tier: haiku
Labels: api
Depends on: — (the client base and the routes of T41 and T42 are on the base branch)
Branch: `p0/i4c-t47-client-links`

## Goal
`ApiClient` offers the link, trace, workflow, schema and reference half of the `ClientInterface` over HTTP: `links_of`, `link_counts`, `expected_links`, `search_linkable`, `trace`, `detect_keys`, `relations`, `default_relation`, the eight link commands, `workflow_status`, `transition`, `form_metadata` and `conformance`. `packages/tl-api/src/tl_api/client/links.py` has the class `LinksApi` with final signatures; the bodies raise `NotImplementedError`. Implementing them is the work. A provided test file (10 tests) must pass.

## Brief references (pasted)
> **4** One client interface for embedded and remote mode. **7** Links: both directions with labels, counts, expected-but-missing, picker search, trace tree. **8** Workflow: states, transitions, guards; a blocked transition reports every guard.
> Errors come back as the embedded exception classes (the base does this): `RecordNotFoundError`, `DuplicateLinkError`, `GuardFailedError` (with `results` as `GuardResult` objects) and so on; do not catch them.

### Specification (the provided tests check it)
Every method makes one request through the base helpers and validates the answer into the tl_core model named in its return type. Put every id into a path with `quote(...)`.
- **`links_of`**: `GET /records/{id}/links` with `include_retracted`; `self._models(LinkView, data)`.
- **`link_counts(record_ids)`**: ids in chunks of `COUNTS_CHUNK` (200): for each chunk `GET /links/counts` with params `{"record_id": chunk}`; merge `{rid: LinkCounts.model_validate(row)}` into one dict. An empty list sends nothing and returns `{}`.
- **`expected_links`**: `GET /records/{id}/expected-links`; `_models(MissingLink, ...)`.
- **`search_linkable(scope, query, ...)`**: `GET /links/search` with `scope`, `q=query`, `record_type`, `exclude_id`, `limit`; `_models(LinkTarget, ...)`.
- **`trace`**: `GET /records/{id}/trace` with `depth`, `direction`; `_model(TraceNode, ...)`.
- **`detect_keys`**: `POST /keys/detect` with body `{"scope": scope, "text": text, "linked_to": linked_to}`; `_models(KeyChip, ...)`.
- **`relations`**: `GET /relations`; `_models(RelationOut, ...)`. **`default_relation`**: `GET /relations/default` with `from_type`, `to_type`; return `DefaultRelationOut.model_validate(data).relation`.
- **The eight link commands**: `self._command("AddLink", cmd)`, `"SuggestLink"`, `"AcceptLink"`, `"DeclineLink"`, `"RepinLink"`, `"VerifyLink"`, `"FlagLink"`, `"RetractLink"`.
- **`workflow_status(record_id, *, roles)`**: `GET /records/{id}/workflow` with params `{"role": list(roles)}`; `_model(WorkflowStatus, ...)`. **`transition`**: `self._command("TransitionWorkflow", cmd)`.
- **`form_metadata`**: `GET /schema/forms` with `scope`, `record_type`; `_model(FormMetadata, ...)`. **`conformance`**: `GET /records/{id}/conformance`; `_model(ConformanceReport, ...)`.
- Imports to add: `quote` from `tl_api.client.base` (extend the import) and `DefaultRelationOut` from `tl_api.models` (extend the import).

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
# packages/tl-api/src/tl_api/client/links.py (the stub; keep every name and signature)
COUNTS_CHUNK = 200
class LinksApi(ApiClientBase):
    def links_of(self, record_id, *, include_retracted=False) -> list[LinkView]
    def link_counts(self, record_ids: Sequence[str]) -> dict[str, LinkCounts]
    def expected_links(self, record_id) -> list[MissingLink]
    def search_linkable(self, scope, query, *, record_type=None, exclude_id=None, limit=20) -> list[LinkTarget]
    def trace(self, record_id, *, depth=2, direction="both") -> TraceNode
    def detect_keys(self, scope, text, *, linked_to=None) -> list[KeyChip];  def relations(self) -> list[RelationOut];  def default_relation(self, from_type, to_type) -> str
    def add_link/suggest_link/accept_link/decline_link/repin_link/verify_link/flag_link/retract_link(self, cmd) -> CommandResult
    def workflow_status(self, record_id, *, roles: Sequence[str] = ()) -> WorkflowStatus;  def transition(self, cmd: TransitionWorkflow) -> CommandResult
    def form_metadata(self, scope, record_type) -> FormMetadata;  def conformance(self, record_id) -> ConformanceReport
# tl_api.models (final): RelationOut(code, label, inverse_code, inverse_label); DefaultRelationOut(relation)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-api/src/tl_api/client/links.py` (the stub)
- `packages/tl-api/src/tl_api/client/base.py`
- `packages/tl-api/tests/harness.py`
- `docs/tickets/P0-I4/provided/test_client_links.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/client/links.py` (edit)
- `packages/tl-api/tests/test_client_links.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T47.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_client_links.py.txt packages/tl-api/tests/test_client_links.py`
2. Implement the methods; delete the `STUB (P0-I4-T47)` paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-api/tests/test_client_links.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_client_links.py.txt packages/tl-api/tests/test_client_links.py
```
Expected: 10 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

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
