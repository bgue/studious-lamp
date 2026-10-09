# P0-I4-T41 — Link read routes

Status: ready
Tier: haiku
Labels: api
Depends on: — (P0-I3 link services are merged; the app and harness are on the base branch)
Branch: `p0/i4c-t41-link-routes`

## Goal
`GET /records/{record_id}/links`, `/records/{record_id}/trace`, `/records/{record_id}/expected-links`, `GET /links/counts` and
`GET /links/search` return real data. `packages/tl-api/src/tl_api/routes/links.py` exists with final signatures, decorators and response
models; the five route bodies raise `NotImplementedError`. Implementing them is the work. A provided test file (9 tests) must pass.

## Brief references (pasted)
> **7.5 API / MCP**: `GET /records/{id}/links?relation=…&depth=…`, `/trace`; MCP `get_links`, `trace`, `follow`.
> **7.4 Surface**: Links tab (inbound and outbound links grouped by relation, with counts, plus expected-but-missing); grid columns and record-header badges use link counts; the link picker searches across types.
> **7.5 Trace view**: an n-hop tree of linked records, e.g. deficiency → inspection → weld → spool → line.

### Specification (the provided test checks it)
Each route makes one `tl_core` call inside `with ctx.backend(True) as uow:` and returns the result. `RecordNotFoundError` is raised by the services and becomes 404 through the existing error table; do not catch it.
- **`get_record_links`**: `link_queries.links_of(uow, record_id, include_retracted=include_retracted)`.
- **`get_record_trace`**: `link_trace.trace(uow, record_id, depth=depth, direction=direction)`.
- **`get_expected_links`**: `missing_expected_links(uow, record_id)`.
- **`get_link_counts`**: `link_queries.link_counts(uow, record_id)` (the query parameter named `record_id` is a list of ids; keep that name).
- **`search_linkable`**: `link_queries.search_linkable(uow, scope, q, record_type=record_type, exclude_id=exclude_id, limit=limit)`.
- Imports to add (the stub omits them so `just check` stays green): `from tl_core.links.expected import MissingLink, missing_expected_links` (extend the existing `MissingLink` import) and `from tl_core.services import link_queries, link_trace`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt`; you copy them into the test tree and must not edit the copy. A `.py.txt` is outside `ruff format`, so the supervisor formatted it already; `diff` it against the original in the last acceptance step.
- The package `tl-api` has a test harness (`packages/tl-api/tests/conftest.py`, `harness.py`): a real app over a real SQLite file. Tests import it with `from harness import ...`. Do not edit it and do not add `__init__.py` to the test directory.
- `just check` includes an OpenAPI drift check (`uv run python -m tl_api.openapi --check`). The stub's signatures, decorators, parameters and response models are final and already in the committed document. If `just check` reports the document out of date, you changed a signature: put it back. Never regenerate or edit `docs/reference/openapi.json`.
- ruff limits lines to 100 columns; run `uv run ruff format packages/tl-api` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/<ticket-id>.md`); it is inside your Allowed paths.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/services/link_queries.py (final)
def links_of(uow: UnitOfWork, record_id: str, *, include_retracted: bool = False) -> list[LinkView]      # RecordNotFoundError
def link_counts(uow: UnitOfWork, record_ids: Sequence[str]) -> dict[str, LinkCounts]
def search_linkable(uow, scope: str, query: str, *, record_type: str | None = None,
                    exclude_id: str | None = None, limit: int = 20) -> list[LinkTarget]
# packages/tl-core/src/tl_core/services/link_trace.py (final)
def trace(uow, record_id: str, *, depth: int = 2, direction: TraceDirection = "both",
          statuses=..., max_nodes: int = 200) -> TraceNode                                               # RecordNotFoundError
# packages/tl-core/src/tl_core/links/expected.py (final)
def missing_expected_links(uow, record_id: str, ...) -> list[MissingLink]                               # RecordNotFoundError
ctx.backend(readonly: bool) -> AbstractContextManager[UnitOfWork]
```
The stub (`packages/tl-api/src/tl_api/routes/links.py`) is the other interface: keep every name, decorator, parameter and annotation.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-api/src/tl_api/routes/links.py` (the stub)
- `packages/tl-api/tests/harness.py`
- `docs/tickets/P0-I4/provided/test_api_links.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/links.py` (edit)
- `packages/tl-api/tests/test_api_links.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T41.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_api_links.py.txt packages/tl-api/tests/test_api_links.py`
2. Implement the five routes; delete the `STUB (P0-I4-T41)` paragraph from the module docstring.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-api/tests/test_api_links.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_api_links.py.txt packages/tl-api/tests/test_api_links.py
```
Expected: 9 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification, or if you think a signature must change.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
