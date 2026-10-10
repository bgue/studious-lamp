# P0-I8-T45 — Dev MCP tool `render_screen`

Status: ready
Tier: haiku
Labels: mcp, tui, tests
Depends on: P0-I8-S41 (merged into the base of this branch)
Branch: `p0/i8c-t45-dev-render-screen`

## Goal
The dev MCP server has a `render_screen` tool: it runs the TUI headless on a copy of the dev ledger, presses a short list of keys, and returns the screen as an SVG snapshot (the format Textual exports), as plain text rows, and the name of the saved SVG file. It never changes the dev ledger.

## Brief references (pasted)
> **Brief 25.3 Dev/ops MCP server:** A development MCP server (local and CI only, never pointed at production data) exposes:
> - **Resources:** schema graph, event catalog, module specs, ADRs, runbooks, sample payloads, TUI screen snapshots, test reports.
> - **Tools:** run tests (filtered), run codegen and report drift, query the dev database, replay or rebuild projections, generate seed data, render a TUI screen to an SVG snapshot, send test webhooks, ...
>
> Coding agents can then inspect the running system, not just the source.
>
> **Decision D12 (fanout P0-I8):** The dev MCP server is a separate entrypoint, `python -m tl_mcp.dev`, on stdio only. It refuses any database that is not a SQLite file under the repo's `dev/` or a temp directory, or a Postgres URL whose database name starts with `tl_test` or `tl_dev`. `query_db` is read-only. `run_tests` takes a marker or path filter from an allow-list, with no shell. `send_test_webhook` only targets loopback receivers.

> **Brief 25.3:** tools include "render a TUI screen to an SVG snapshot". **Brief 25.4:** TUI snapshot tests (Textual snapshot testing of key screens and key bindings).

### Facts the supervisor measured (2026-10-10)
This runs in about 0.5 s and gives a 54 KB SVG for a 120 x 40 screen:
```python
from tl_tui.main import build_app          # build_app(db, project="P123", *, live=True) -> TlApp
app = build_app(db_path, "P123", live=False)   # live=False: no change-feed pollers
async with app.run_test(size=(120, 40)) as pilot:
    await pilot.pause()
    await pilot.press("enter")                 # key names are Textual's: "enter", "f2", "ctrl+p", "slash", "down" ...
    await pilot.pause()
    svg = app.export_screenshot(title="t")     # str, an <svg ...> document
    strips = app.screen._compositor.render_strips()
    text = "\n".join(strip.text.rstrip() for strip in strips)   # the screen as plain rows
```
`tests/helpers.screen_text` in `packages/tl-tui/tests/helpers.py` does the last two lines (with a pyright ignore for the private `_compositor`; do the same, once, with a comment).
The app opens the SQLite ledger it is given, and its forms can write (`Ctrl+S` in an edit form saves, `n` makes a record), so the tool must never hand it the dev ledger itself.

### The dev server this ticket plugs into (already merged)
`packages/tl-mcp/src/tl_mcp/dev/` holds the server core. Each tool or resource group is one module with `register(server, ctx)`; `server.py` calls them all. Your module is a stub today (`def register(...): del server, ctx`). Replace its body; keep the function name and signature. The shared pieces, verbatim:

```python
# packages/tl-mcp/src/tl_mcp/dev/runtime.py
class DevContext:
    """The repository, the one database the dev tools use, and where they write.

    ``audit_path=None`` turns the audit file off (tests). ``target`` is already checked by
    :func:`tl_mcp.dev.guard.resolve_target`; a tool never builds its own.
    """

    repo_root: Path
    target: DevTarget
    audit_path: Path | None = None
    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))

    @property
    def dev_dir(self) -> Path:
        return self.repo_root / "dev"

    @property
    def data_dir(self) -> Path:
        """``dev/data``: git-ignored; reports and snapshots the tools write go below it."""
        return self.dev_dir / "data"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "test-reports"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    def child_env(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        """A minimal environment for a child process: allow-listed variables plus ``extra``.

        ``TL_ENV`` is always ``dev``, so the child never sees a real environment's settings.
        """
        env = {k: self.environ[k] for k in CHILD_ENV_KEYS if k in self.environ}
        env["TL_ENV"] = "dev"
        env.update(extra or {})
        return env
```

```python
# packages/tl-mcp/src/tl_mcp/dev/runtime.py  (every tool body runs inside it)
def guarded(
    ctx: DevContext,
    tool: str,
    detail: Mapping[str, Any] | None = None,
    *,
    error: type[Exception] = ToolError,
) -> Iterator[None]:
    """Run a tool body: audit the call and map expected failures to ``error`` with a clear text."""
    info = dict(detail or {})
    try:
    ...
```
`guarded` writes one audit line per call and turns a `DevGuardError` into a `ToolError("refused: ...")`, a `DevToolFailure` into a `ToolError` with its own text, and `ValueError`/`LookupError`/`OSError` into short `ToolError`s. Raise `DevGuardError` (from `tl_mcp.dev.errors`) to refuse a request and `DevToolFailure` for "it ran and failed"; do not build your own error texts around paths.

The finished tool of this server, `query_db`, is your pattern; copy its shape (decorator, `Annotated[..., Field(...)]` parameters, output model, `with guarded(...)` around the body):

```python
# packages/tl-mcp/src/tl_mcp/dev/tool_query_db.py
"""``query_db``: read-only SQL on the dev database (brief 25.3, FANOUT D12)."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from tl_lake.guard import MAX_SQL_CHARS

from tl_mcp.dev import query
from tl_mcp.dev.runtime import DevContext, guarded

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)


class QueryDbOutput(BaseModel):
    """The answer of ``query_db``."""

    dialect: str  # "sqlite" or "postgres"
    columns: list[str]
    rows: list[list[Any]]  # JSON values, in column order
    row_count: int
    truncated: bool  # more rows existed than were returned
    truncated_by: str | None  # "limit" or "bytes"
    limit: int
    elapsed_ms: float


def register(server: MCPServer, ctx: DevContext) -> None:
    @server.tool(annotations=READ_ONLY)
    def query_db(
        sql: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_SQL_CHARS,
                description="One SELECT (or WITH ... SELECT) statement.",
            ),
        ],
        limit: Annotated[
            int, Field(ge=1, le=query.MAX_LIMIT, description="Maximum rows to return.")
        ] = query.DEFAULT_LIMIT,
    ) -> QueryDbOutput:
        """Run read-only SQL on the dev database (a SQLite file under dev/ or a temp directory, or a
        local tl_test*/tl_dev* Postgres).

        Only one SELECT or WITH ... SELECT is accepted: no DDL, DML, PRAGMA, ATTACH, SET or stacked
        statements. Tables are `events` (the ledger), the `cur_*` current-state tables, `wh_*`
        webhook state and `outbox_events`; `wh_secret` cannot be read. On SQLite
        `SELECT name, sql FROM sqlite_master` lists the tables. Rows (default 100, at most 1000),
        result size (1 MiB) and time (10 s) are limited.
        """
        with guarded(ctx, "query_db", {"sql": sql, "limit": limit}):
            result = query.run_query(ctx.target, sql, limit)
            return QueryDbOutput(
                dialect=result.dialect,
                columns=result.columns,
                rows=result.rows,
                row_count=len(result.rows),
                truncated=result.truncated,
                truncated_by=result.truncated_by,
                limit=result.limit,
                elapsed_ms=result.elapsed_ms,
            )
```

The test harness (`packages/tl-mcp/tests/dev_harness.py`) and the fixture that gives you a server over a fresh SQLite ledger in `tmp_path`:

```python
# packages/tl-mcp/tests/dev_harness.py  (the class, without its helper bodies)
class DevHarness:
    ctx: DevContext
    server: MCPServer
    db: Path

    @staticmethod
    def build(
        root: Path,
        *,
        repo_root: Path | None = None,
        target: DevTarget | None = None,
        create: bool = True,
    ) -> DevHarness:
        """A server over ``root / "tl.db"`` (a temp directory, so the guard accepts it).

        ``repo_root`` defaults to the real repository (tools such as ``gen`` and ``run_tests`` need
        it); tools that write below it (reports, snapshots) must be given a copy or a temp tree.
        The audit file is ``root / "audit.jsonl"``.
        """
        db = root / "tl.db"
        if create and target is None:
            create_schema(db)
        repo = repo_root if repo_root is not None else find_repo_root()
        chosen = target if target is not None else resolve_target(db, repo_root=repo)
        ctx = DevContext(repo_root=repo, target=chosen, audit_path=root / "audit.jsonl")
        return DevHarness(ctx, build_dev_server(ctx), db)

    def create_record(self, key: str, title: str = "A record", scope: str = "project:P123") -> str:
        """Append a ``core.Record`` to the ledger (as ``user:seed``); returns the stream id."""
        from tl_adapters.sqlite.uow import open_uow
        from tl_core.services.commands import CreateRecord
        from tl_core.services.records import handle_create_record

        with open_uow(self.db) as uow:
            result = handle_create_record(
                uow,
                CreateRecord(
                    actor="user:seed",
                    source="test",
                    scope=scope,
                    record_type="core.Record",
                    title=title,
                    key=key,
                ),
            )
        return result.stream_id

    def call(self, tool: str, **arguments: Any) -> CallToolResult:
        result = asyncio.run(self.server.call_tool(tool, arguments))
        assert isinstance(result, CallToolResult)
        return result

    def structured(self, tool: str, **arguments: Any) -> Any:
        result = self.call(tool, **arguments)
        assert not result.is_error
        assert result.structured_content is not None
        return result.structured_content

    def read(self, uri: str) -> str:
        contents: list[Any] = list(asyncio.run(self.server.read_resource(uri)))
        assert len(contents) == 1
        content = contents[0].content
        assert isinstance(content, str)
        return content

    def tool_names(self) -> list[str]:
        return sorted(tool.name for tool in asyncio.run(self.server.list_tools()))

    def resource_uris(self) -> list[str]:
        listed = asyncio.run(self.server.list_resources())
        templates = asyncio.run(self.server.list_resource_templates())
        return sorted([str(r.uri) for r in listed] + [str(t.uri_template) for t in templates])
    ...
# packages/tl-mcp/tests/conftest.py
def dev_env(tmp_path: Path) -> Iterator[DevHarness]:
    """The dev MCP server over a fresh SQLite ledger in ``tmp_path``."""
    yield DevHarness.build(tmp_path)
```
`env.call("tool", **args)` runs the tool as a client's `tools/call` would (a refusal raises `ToolError`); `env.structured(...)` returns the structured result; `env.audit_lines()` returns the audit records.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/dev/tool_render_screen.py` (the stub you replace)
- `packages/tl-mcp/src/tl_mcp/dev/tool_query_db.py` (the pattern)
- `packages/tl-tui/src/tl_tui/main.py` (read `build_app` only)
- `packages/tl-tui/tests/helpers.py`
- `packages/tl-mcp/tests/dev_harness.py`
may explore: `packages/tl-tui/src/tl_tui/keymap.py` (to pick key names for the tests)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/dev/tool_render_screen.py` (replace the stub)
- `packages/tl-mcp/tests/test_dev_render_screen.py` (create)

## Steps
1. Tool `render_screen` is `async def` (Textual's `run_test` is a coroutine). Parameters: `project: str = "P123"` (`max_length=64`, pattern `^[A-Za-z0-9_.-]+$`), `keys: list[str] = []` (at most 20 items, each `max_length=30` and matching `^[A-Za-z0-9_+]+$`; Textual names like `enter`, `down`, `f2`, `ctrl+p`), `width: int = 120` (`ge=40, le=200`), `height: int = 40` (`ge=10, le=60`), `name: str | None` (`max_length=60`, pattern `^[A-Za-z0-9_-]+$`; the file name stem, default `screen`). Annotation `ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)` (it saves a file below `dev/data/snapshots/`).
2. Inside `guarded(ctx, "render_screen", {...})`: refuse (`DevGuardError`) unless `ctx.target.kind == "sqlite"` ("render_screen needs a SQLite dev database"); raise `DevToolFailure` if the database file does not exist.
3. Copy the ledger: `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` as source, `.backup(dest)` into `<tempfile.mkdtemp()>/tl.db`, close both. Run the app on the copy. Remove the temporary directory in a `finally`.
4. `app = build_app(copy, project, live=False)`; `async with app.run_test(size=(width, height)) as pilot:` press the keys one by one (`await pilot.press(key)`, `await pilot.pause()` after each), pause once more, export the SVG and the plain text. Wrap the whole run in `asyncio.wait_for(..., timeout=30)`; a timeout is a `DevToolFailure("the screen did not settle within 30 s")`. Close the app's client afterwards the way `tl_tui.main.run` does (`app.client.close` when it exists).
5. Save the SVG to `ctx.snapshots_dir / f"{name or 'screen'}.svg"` (create the directory; write to a temporary name in the same directory and `os.replace` it, so a reader never sees half a file). Result model `ScreenOutput`: `svg: str` (the document; if longer than 400000 characters return `""` and set `svg_truncated: bool = True`), `text: str` (plain rows, at most 20000 characters), `file: str` (repository-relative path, e.g. `dev/data/snapshots/screen.svg`), `width: int`, `height: int`, `keys: list[str]`.
6. The docstring says that the ledger is copied first so keys never write to it, lists useful keys (`f1` help, `f2`/`f3` panels, `enter` open record, `slash` filter) and says the TUI opens `project:<project>`.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_dev_render_screen.py -q
uv run pytest packages/tl-mcp -q
```
Expected: all pass.

## Tests to add
`packages/tl-mcp/tests/test_dev_render_screen.py` (use `DevHarness.build(tmp_path, repo_root=<a copy tree>)` so snapshots go to a temporary `dev/data/snapshots/`: make `tmp_path / "repo"` with `AGENTS.md`, `justfile`, `dev/`; the database stays at `tmp_path / "tl.db"`; seed it with `env.create_record("V-1", "Valve one", scope="project:P123")` and a second record):
- Basic: `render_screen()` returns an `svg` starting with `<svg`, `text` containing `V-1` and `Valve one`, `file == "dev/data/snapshots/screen.svg"` and that file exists and equals `svg`.
- Keys change the screen: `keys=["enter"]` shows the record view (the text contains `Details` and `V-1`) and differs from the keyless text; `keys=["f1"]` shows a key map; an unknown key name (`"nokey"`) gives a `ToolError`, not a hang.
- Size: `width=80, height=24` gives text rows of at most 80 characters and at most 24 rows.
- Read-only: press the keys that open the new-record form, type a title and save (`n`, then letters, then `ctrl+s`); afterwards `SELECT count(*) FROM cur_core_record` on the real ledger is unchanged and the ledger file's bytes are identical (compare a SHA-256 before and after).
- Another project (`project="P999"`) renders an empty grid, not an error.
- Postgres target refused (`resolve_target("postgresql://postgres:x@localhost/tl_test", repo_root=...)` needs no server): `ToolError` matching `refused`. Missing database file: `ToolError` matching `does not exist`.
- Schema refusals: 21 keys, a key with a space, `width=500`, `name="../x"` are rejected (`ToolError`) and write no file.
- Two calls with different `name` values leave two files; the same name replaces the file.
- No temporary directory is left behind (count entries of `tempfile.gettempdir()` that start with the prefix you pass to `mkdtemp`: use `prefix="tl-render-"`).

## Report requirements
Standard report. Paste the output of the three acceptance commands. Say how long the whole test file takes.

## Escalation triggers
- Stop and report *Blocked* if `app.run_test` cannot run inside the tool's event loop (say what error you got); the supervisor will move the render to a child process.
- Stop if `export_screenshot` needs a terminal.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
