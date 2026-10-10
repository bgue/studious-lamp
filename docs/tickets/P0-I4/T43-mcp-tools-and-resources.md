# P0-I4-T43 — MCP read tool and resource bodies

Status: ready
Tier: haiku
Labels: mcp
Depends on: — (the server, tool schemas, authorise hook and error mapping are on the base branch)
Branch: `p0/i4c-t43-mcp-tools`

## Goal
The MCP server (`tl_mcp.server.build_server`) already registers four read tools (`search_records`, `get_record`, `get_links`, `trace`) and three resources (`tl://record/{scope}/{key}`, `tl://schema/{scope}/{record_type}`, `tl://relations`), with their schemas, the authorise hook and the error mapping. The seven bodies in `packages/tl-mcp/src/tl_mcp/tools.py` (plus the helper `resolve_record_id`) and `resources.py` raise `NotImplementedError`. Implementing them is the work. Two provided test files (10 and 4 tests) must pass.

## Brief references (pasted)
> **11.3 MCP** Resources: record by key/URI, schema/model docs. Tools: `search_records`, `get_record`, `get_links`, `trace`. All tool calls run with the invoking identity and are tagged `source=mcp:{agent}`; Phase 0 has no write tools.
> **O3 (orchestrator decision)** MCP `search_records` takes the same `q` text as the REST API; the server parses it (`tl_core.query.parse`) and a syntax error is reported with its position.
> **7.5** `GET /records/{id}/links`, `/trace`; MCP `get_links`, `trace`.

### Specification (the provided tests check it)
Every body runs inside `guarded(...)` (already in `server.py`): the authorise hook has been called and an expected failure (`ServiceError`, `ConcurrencyError`, `ValueError`, `QuerySyntaxError`, `ApiError`) becomes a tool or resource error with a readable message, so the bodies just let exceptions propagate. Each body opens a read-only unit of work with `with ctx.factory(True) as uow:` and calls the services. No SQL, no rules.
- **`resolve_record_id(uow, record, scope)`**: `found = queries.get_record_by_id(uow, record)`; if `found is None and scope is not None`, `found = queries.get_record(uow, scope, record)`. If still `None`, `raise RecordNotFoundError(f"no record {record!r}{where}")` where `where` is `f" in scope {scope!r}"` when `scope` is given, else `" (give `scope` to look up a key)"`. Return `str(found["id"])`.
- **`search_records_impl`**: `spec = build_spec(scope, q, limit=limit, offset=offset, order_by=order_by)` (from `tl_api.routes.records`; it parses `q` and `order_by` exactly as `GET /records` does and raises `QuerySyntaxError` / `ApiError`). In `with ctx.factory(True) as uow:` return `SearchResult(records=run_query(uow, spec), total=count_query(uow, spec), limit=limit, offset=offset)`.
- **`get_record_impl`**: inside the `with`, `record_id = resolve_record_id(uow, record, scope)`, `found = queries.get_record_by_id(uow, record_id)`; `assert found is not None`; return `found` (after the `with`).
- **`get_links_impl`**: `resolve_record_id`, then `link_queries.links_of(uow, record_id, include_retracted=include_retracted)`.
- **`trace_impl`**: `resolve_record_id`, then `link_trace.trace(uow, record_id, depth=depth, direction=direction)`.
- **`record_resource(ctx, scope, key)`**: `found = queries.get_record(uow, scope, key)`; if `None`, `raise RecordNotFoundError(f"no record with key {key!r} in scope {scope!r}")`; `links = link_queries.links_of(uow, found["id"])`; return `dump({"record": found, "links": [link.model_dump(mode="json") for link in links]})`.
- **`schema_resource(ctx, scope, record_type)`**: `meta = psets.form_metadata(uow, scope, record_type)`; return `dump(meta.model_dump(mode="json"))`.
- **`relations_resource(ctx)`** (no database): `vocabulary = get_vocabulary()`; for each `code in vocabulary.codes()`, `relation = vocabulary.get(code)` and a dict with `code`, `label`, `inverse_code`, `inverse_label`; return `dump(rows)`.
- `dump(data)` is given. Imports to add (the stubs omit them so `just check` stays green): in `tools.py` `from tl_api.routes.records import build_spec`, `from tl_core.query import count_query, run_query`, `from tl_core.services import link_queries, link_trace, queries`, `from tl_core.services.errors import RecordNotFoundError`; in `resources.py` `from tl_core.links.provider import get_vocabulary`, `from tl_core.services import link_queries, psets, queries`, `from tl_core.services.errors import RecordNotFoundError`. Keep `ruff`'s import order (third-party block, then `tl_*` is first-party in `src`).

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt`; you copy them into the test tree and must not edit the copy. The supervisor formatted them already; `diff` the copy against the original in the last acceptance step.
- The test harnesses (`packages/tl-api/tests/conftest.py`, `harness.py`; `packages/tl-mcp/tests/conftest.py`, `mcp_harness.py`) run a real app or server over a real SQLite file. Tests import them with `from harness import ...` / `from mcp_harness import ...`. Do not edit them and do not add `__init__.py` to a test directory.
- `just check` includes an OpenAPI drift check. You change no route, so it must stay green; never regenerate or edit `docs/reference/openapi.json`.
- ruff limits lines to 100 columns; run `uv run ruff format packages` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/<ticket-id>.md`); it is inside your Allowed paths.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-mcp/src/tl_mcp/context.py (final)
@dataclass(frozen=True)
class McpContext: factory: UowFactory; actor: str; authorize: Authorizer     # ctx.factory(readonly) -> context manager yielding a UnitOfWork
# packages/tl-mcp/src/tl_mcp/models.py (final)
class SearchResult(BaseModel): records: list[dict[str, Any]]; total: int; limit: int; offset: int
# packages/tl-api/src/tl_api/routes/records.py (final)
def build_spec(scope: str, q: str | None, *, record_type=None, status=None, include_voided=False, limit: int | None = 500, offset: int = 0, order_by: str | None = None) -> QuerySpec
# tl_core (final)
run_query(uow, spec) -> list[dict]; count_query(uow, spec) -> int
queries.get_record(uow, scope, key) -> dict | None; queries.get_record_by_id(uow, record_id) -> dict | None
link_queries.links_of(uow, record_id, *, include_retracted=False) -> list[LinkView]
link_trace.trace(uow, record_id, *, depth=2, direction="both") -> TraceNode
psets.form_metadata(uow, scope, record_type) -> FormMetadata
get_vocabulary() -> RelationVocabulary   # .codes() -> list[str]; .get(code) -> Relation(code, label, inverse_code, inverse_label)
```
The stubs (`tools.py`, `resources.py`) are the other interface: keep every name, keyword-only parameter and annotation.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-mcp/src/tl_mcp/tools.py` and `resources.py` (the stubs)
- `packages/tl-mcp/src/tl_mcp/server.py` (how the bodies are called)
- `packages/tl-mcp/tests/mcp_harness.py`
- `docs/tickets/P0-I4/provided/test_mcp_tools.py.txt` and `test_mcp_resources.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/tools.py` (edit)
- `packages/tl-mcp/src/tl_mcp/resources.py` (edit)
- `packages/tl-mcp/tests/test_mcp_tools.py` and `packages/tl-mcp/tests/test_mcp_resources.py` (create: byte-for-byte copies of the provided files)
- `docs/reports/P0-I4/P0-I4-T43.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_mcp_tools.py.txt packages/tl-mcp/tests/test_mcp_tools.py` and the same for `test_mcp_resources`.
2. Implement the helper and the seven bodies; delete the `STUB (P0-I4-T43)` paragraph from both module docstrings.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-mcp -q
just check
just test
diff docs/tickets/P0-I4/provided/test_mcp_tools.py.txt packages/tl-mcp/tests/test_mcp_tools.py
diff docs/tickets/P0-I4/provided/test_mcp_resources.py.txt packages/tl-mcp/tests/test_mcp_resources.py
```
Expected: 21 tests pass in `packages/tl-mcp` (7 server tests already there, 10 + 4 provided), `just check` and `just test` exit 0, both `diff`s print nothing.

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
