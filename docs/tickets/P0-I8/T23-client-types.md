# P0-I8-T23 — ApiClient methods for extension types

Status: ready
Tier: haiku
Labels: api
Depends on: T21 (the routes), merged on `p0/i8b`
Branch: `p0/i8b-t23-client-types`

## Goal
`ApiClient` can call the extension type routes: `list_types`, `get_type`, `create_instance`, `get_record_body` and `put_record_body`. Each returns the model the embedded services
return and raises the embedded exception class for a failure (the base class already maps the error codes). The remote TUI client (a later ticket) is built on these.

## Brief references (pasted)
> §31.3 extension types get ... generic API (`/records/{type}`) and MCP tools, generic TUI grid and forms (from LinkML + `form.yaml`).
> §31.2 Through Throughline (TUI/API/MCP): the body is validated, stored as an object, then a metadata event referencing its hash is appended. Updates are new document versions.
>
> The routes (T21): `GET /types?status=`, `GET /types/{type_ref}`, `POST /types/{type_name}/records` (JSON body `scope`, `title`, optional `key`, `description`, `psets`, `body`,
> `numbering`), `GET /records/{id}/body`, `PUT /records/{id}/body` (JSON body `scope`, `body`, optional `expected_version`).

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_api/client/base.py
class ApiClientBase:
    def _get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any: ...   # None params are dropped
    def _post_json(self, path: str, body: Any, params=None) -> Any: ...
    def _send(self, method: str, path: str, *, params=None, json: Any = None, content=None, headers=None) -> httpx2.Response: ...
    def _model(model, data): ...; def _models(model, data) -> list: ...
def quote(segment: str) -> str: ...     # for a value that goes into a path
# tl_core/extypes/service.py: TypeSummary, TypeDetail, BodyView, BodyStoredOut (pydantic models)
# tl_core/services/commands.py: CommandResult
```
The stub `packages/tl-api/src/tl_api/client/types_api.py` has the class, signatures and docstrings; it is already part of `ApiClient`. Replace each
`raise NotImplementedError("STUB (P0-I8-T23)")`. Do not change a signature.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/client/types_api.py` (the stub)
- `packages/tl-api/src/tl_api/client/proposals.py` (a finished group of the same shape)
- `docs/tickets/P0-I8/provided/b-test_client_types.py.txt` (the test to make pass)
- `packages/tl-api/src/tl_api/routes/extypes.py` (read only: the routes the client calls)
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/client/types_api.py` (replace the stub bodies)
- `packages/tl-api/tests/test_client_types.py` (create: copy of the provided file, unchanged)
- `docs/reports/P0-I8/P0-I8-T23.md` (create: your report; commit it)

## Steps
1. `uv sync --all-packages`. Run every command from the repository root.
2. `cp docs/tickets/P0-I8/provided/b-test_client_types.py.txt packages/tl-api/tests/test_client_types.py`. Do not edit it.
3. Fill in the five methods.

## Acceptance
```
just check
uv run pytest packages/tl-api/tests/test_client_types.py -q
uv run pytest packages/tl-api -q
```
Expected: `just check` clean; 9 passed in `test_client_types.py`; the rest of `packages/tl-api` still passes.

## Tests to add
- `packages/tl-api/tests/test_client_types.py`: the provided file (listing and filtering, the detail with its form, an unknown ref, create for a managed and an object-backed type,
  the embedded error classes, put and read of a body with a stale version, quarantine and healing, an agent token).

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Rules to remember (from the project's learnings)
- Ruff's line limit is 100 columns, including docstrings and comments. Write files with the Write or Edit tool, not shell heredocs. Never use `pkill -f`.
- Never name a module `types.py`. Run Python from the repository root.
- Commit as `P0-I8-T23: <summary>` with the report in the same commit. Delete the stub's `# ruff: noqa: F401` first line once ruff has no unused import left.

## Escalation triggers
- Stop and report *Blocked* if a docstring and the provided test disagree, if a function listed under Interfaces is missing or has another signature, or if you would have to touch a
  file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
