# P0-I8-T22 — MCP tools and resources for extension types

Status: ready
Tier: haiku
Labels: mcp
Depends on: S23 (body store), S24 (`type_detail`, `McpContext.objects`), merged on `p0/i8b`
Branch: `p0/i8b-t22-mcp-type-tools`

## Goal
An MCP agent can discover and read extension types: the tools `list_record_types`, `get_record_type` and `get_record_body` and the resources `tl://types` and `tl://types/{type_ref}`.
All are read-only. Creating an instance stays what it already is for every record type: `create_record` with `record_type="co.acme.SafetyObservation"` records a *proposal* that a person
accepts (propose-only, FANOUT D3); an object-backed type is refused there with a message that says it needs a body. That behaviour is already in place; the provided test checks it.

## Brief references (pasted)
> §31.3 Because they share the envelope, extension types get ... generic API (`/records/{type}`) and MCP tools, generic TUI grid and forms (from LinkML + `form.yaml`) ...
>
> §31.4 Bodies are never trusted without validation. Hashes are verified on read, and mismatches are quarantined. Index fields are the query contract.
>
> §11.3 (MCP): record-changing tools are propose-only in Phase 0. `get_record_body` returns a body only after its hash verified; on a mismatch the record is quarantined, the body is
> not returned and the tool fails with the service's message (`guarded` turns the service error into a `ToolError`).

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_mcp/context.py
class McpContext:  factory: UowFactory; actor: str; authorize: Authorizer; lake: LakeQueryService; objects: ObjectStore | None
    # ctx.factory(True) yields a read-only unit of work; ctx.factory is also what read_body takes
# tl_mcp/tools.py
def resolve_record_id(uow, record: str, scope: str | None) -> str: ...   # id or key (with scope); RecordNotFoundError
# tl_mcp/resources.py
def dump(data: Any) -> str: ...                                          # canonical JSON text
# tl_mcp/errors.py
def guarded(ctx, tool: str, resource: str, *, error=ToolError, parts=...): ...   # already used by register_type_tools
# tl_core/extypes/registry.py
def list_types(conn, *, status: TypeStatus | None = None) -> list[TypeView]: ...
# tl_core/extypes/service.py
def type_detail(uow, type_ref: str) -> TypeDetail: ...                   # UnknownTypeError when unknown
# tl_core/extypes/body.py
def body_pointer(conn, stream_id: str) -> BodyPointer | None: ...
def read_body(factory, store, *, stream_id: str) -> dict[str, Any]: ...  # quarantines on a mismatch, then raises
# tl_core/extypes/service.py
class TypeSummary(BaseModel): ...; class BodyView(BaseModel): record_id: str; pointer: BodyPointer; body: dict[str, Any]
def summarise(view: TypeView) -> TypeSummary: ...      # given: use it
```
The stub `packages/tl-mcp/src/tl_mcp/type_tools.py` has `register_type_tools` complete (names, schemas, descriptions, the guarded wrappers) and five unfinished functions with docstrings:
`list_record_types_impl`, `get_record_type_impl`, `get_record_body_impl`, `types_resource` and `type_resource`. Replace each `raise NotImplementedError("STUB (P0-I8-T22)")`. Do not change
`register_type_tools`: its signatures and descriptions are the tool contract, and `build_server` already calls it.

**Independence.** This ticket needs nothing from T21 or T20: the models and `summarise` are in `tl_core.extypes.service`, merged.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/type_tools.py` (the stub)
- `packages/tl-mcp/src/tl_mcp/tools.py` (finished impl functions of the same shape)
- `docs/tickets/P0-I8/provided/b-test_mcp_type_tools.py.txt` (the test to make pass)
- `packages/tl-mcp/tests/mcp_harness.py` (read only)
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/type_tools.py` (replace the stub bodies)
- `packages/tl-mcp/tests/test_mcp_type_tools.py` (create: copy of the provided file, unchanged)
- `docs/reports/P0-I8/P0-I8-T22.md` (create: your report; commit it)

## Steps
1. `uv sync --all-packages`. Run every command from the repository root.
2. `cp docs/tickets/P0-I8/provided/b-test_mcp_type_tools.py.txt packages/tl-mcp/tests/test_mcp_type_tools.py`. Do not edit it.
3. Fill in the five functions.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_mcp_type_tools.py -q
uv run pytest packages/tl-mcp -q
```
Expected: `just check` clean except the known failure below; 15 passed in `test_mcp_type_tools.py`; all other MCP tests pass.
Known and not yours: `uv run pytest packages/tl-schema` fails `test_every_event_type_the_code_names_is_in_the_catalog` (another workstream's event types). Do not run or fix it.

## Tests to add
- `packages/tl-mcp/tests/test_mcp_type_tools.py`: the provided file. It covers the tool surface (read-only annotations), listing and filtering, the form, a quarantined version's report,
  an unknown ref, the body by id and by key, a damaged body (never returned, quarantined), no object store, the two resources, and propose-only create for a managed type, an
  object-backed type and an unregistered type.

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Rules to remember (from the project's learnings)
- Every string an MCP tool accepts needs a `maxLength` (a test walks all tool schemas); `register_type_tools` already has them. Do not add a tool argument.
- Ruff's line limit is 100 columns, including docstrings. Write files with the Write or Edit tool. Never use `pkill -f`. Commit as `P0-I8-T22: <summary>`, report included.

## Escalation triggers
- Stop and report *Blocked* if a docstring and the provided test disagree, or if you would have to touch a file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
