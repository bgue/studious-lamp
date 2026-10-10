# P0-I8-T04 — MCP `get_settings`

Status: merged
Tier: haiku
Labels: mcp
Depends on: — (the tool is registered in `server.py`; its body is the stub)
Branch: `p0/i8a-t04-mcp-get-settings`

## Goal
An AI agent can read settings over MCP: the read tool `get_settings` (already registered in `tl_mcp/server.py`, with its parameter schema and description) returns each setting with its definition and its effective state for a project, one setting by `key` or a list narrowed by `prefix` and `modified_only`. The body `tools.get_settings_impl` raises `NotImplementedError`; a provided test file (7 tests) must pass.

## Brief references (pasted)
> **30.4 Interfaces.** MCP: `get_settings` (read), `propose_setting_change` (draft for human approval).
> **11.3** MCP read tools never change anything; they run inside the authorise hook (`guarded`) and a read-only unit of work.

### Specification
The stub's docstring gives the exact steps. `server.py` already calls `tools.get_settings_impl(ctx, key=..., prefix=..., project=..., modified_only=...)` inside `guarded`, which turns `ServiceError` and `ValueError` into tool errors the agent reads; you do not catch anything. `SettingView` is `(definition, effective)`; `list_views` sorts by key. A `key` together with a `prefix` or `modified_only=True` is a `ValueError("give a key, or a prefix and a filter, not both")`. Do not touch `server.py`.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I8/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I8/<ticket-id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring and from every docstring or comment you fill in.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py` (it shadows the standard library); run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. The base is green: if a test outside your Allowed paths fails, report it under *Blocked* with the output.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-mcp/src/tl_mcp/tools.py (the stub you complete)
def get_settings_impl(
    ctx: McpContext,
    *,
    key: str | None,
    prefix: str | None,
    project: str | None,
    modified_only: bool,
```
```python
# imports to add to tools.py (the stub's autofix removed them):
from tl_core.settings.views import SettingView, get_view, list_views
# SettingView(definition: SettingDefinition, effective: EffectiveSetting)
# list_views(conn, *, project=None, user=None, prefix=None, modified_only=False) -> list[SettingView]
# get_view(conn, key, *, project=None, user=None) -> SettingView          # UnknownSettingError ("there is no setting 'x'")
# ctx.factory(True) -> context manager yielding an entered read-only UnitOfWork (uow.conn() is the connection)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-mcp/src/tl_mcp/tools.py`
- `packages/tl-mcp/tests/mcp_harness.py` (what the provided test builds on; read only)
- `docs/tickets/P0-I8/provided/t04-test_mcp_get_settings.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/tools.py` (edit: the body of `get_settings_impl` and its import)
- `packages/tl-mcp/tests/test_mcp_get_settings.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I8/P0-I8-T04.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I8/provided/t04-test_mcp_get_settings.py.txt packages/tl-mcp/tests/test_mcp_get_settings.py`
2. Implement `get_settings_impl`; delete the STUB paragraph; add the import.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-mcp/tests/test_mcp_get_settings.py -q
just check
uv run pytest packages/tl-mcp -q
```
Expected: 7 tests pass; `just check` clean; the MCP package is green (it includes the schema test that every string argument has a `maxLength`).

## Tests to add
None beyond the provided file.

## Report requirements
Standard report.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo.

## Blocked
(implementer writes here)

## Decision
Reviewed in a fresh context: pass. Merged into p0/i8a as 9235f2a.
