# P0-I8-T40 — Dev MCP tool `run_tests`

Status: merged
Tier: haiku
Labels: mcp, tests
Depends on: P0-I8-S41 (merged into the base of this branch)
Branch: `p0/i8c-t40-dev-run-tests`

## Goal
The dev MCP server has a `run_tests` tool. An agent names test paths, a marker, a keyword and adapters from the allow-lists; the tool runs one filtered pytest in a child process (no shell), stores the full output as a report under `dev/data/test-reports/`, and returns the counts, the summary line and the tail of the output.

## Brief references (pasted)
> **Brief 25.3 Dev/ops MCP server:** A development MCP server (local and CI only, never pointed at production data) exposes:
> - **Resources:** schema graph, event catalog, module specs, ADRs, runbooks, sample payloads, TUI screen snapshots, test reports.
> - **Tools:** run tests (filtered), run codegen and report drift, query the dev database, replay or rebuild projections, generate seed data, render a TUI screen to an SVG snapshot, send test webhooks, ...
>
> Coding agents can then inspect the running system, not just the source.
>
> **Decision D12 (fanout P0-I8):** The dev MCP server is a separate entrypoint, `python -m tl_mcp.dev`, on stdio only. It refuses any database that is not a SQLite file under the repo's `dev/` or a temp directory, or a Postgres URL whose database name starts with `tl_test` or `tl_dev`. `query_db` is read-only. `run_tests` takes a marker or path filter from an allow-list, with no shell. `send_test_webhook` only targets loopback receivers.

The allow-list logic already exists in the guard. `select_pytest_args` returns the argument list that follows `python -m pytest`, or raises `DevGuardError`; it accepts only: `marker` in `parity`, `requires_postgres`; `keyword` of letters, digits, `_`, spaces and parentheses; `paths` under `packages/<pkg>/tests` or `tests` (optionally `::test_name`), each existing; `adapters` in `sqlite`, `postgres`, `sqlite,postgres`.

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-mcp/src/tl_mcp/dev/guard.py
def select_pytest_args(
    *,
    repo_root: Path,
    paths: Sequence[str] = (),
    marker: str | None = None,
    keyword: str | None = None,
    adapters: str | None = None,
) -> list[str]:
    ...
```
```python
# packages/tl-mcp/src/tl_mcp/dev/guard.py
def resolve_postgres(raw: str) -> DevTarget:
    ...
```
(`resolve_postgres` returns the target for a local Postgres URL whose database starts with `tl_test` or `tl_dev`, and raises `DevGuardError` otherwise; you only call it.)

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
- `packages/tl-mcp/src/tl_mcp/dev/tool_run_tests.py` (the stub you replace)
- `packages/tl-mcp/src/tl_mcp/dev/tool_query_db.py` (the pattern)
- `packages/tl-mcp/src/tl_mcp/dev/guard.py` (read `select_pytest_args` and `resolve_postgres` only)
- `packages/tl-mcp/src/tl_mcp/dev/runtime.py`
- `packages/tl-mcp/tests/dev_harness.py`
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/dev/tool_run_tests.py` (replace the stub)
- `packages/tl-mcp/tests/test_dev_run_tests.py` (create)

## Steps
1. Tool signature (all keyword; every string and list bounded):
   - `paths: list[str]` (at most 20 items, each at most 200 characters), default empty;
   - `marker: Literal["parity", "requires_postgres"] | None`;
   - `keyword: str | None` (`max_length=200`);
   - `adapters: Literal["sqlite", "postgres", "sqlite,postgres"] | None`;
   - `timeout_s: int` (`ge=1, le=900`, default 300).
   Annotate it `ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)` (it writes a report file).
2. Inside `guarded(ctx, "run_tests", {...the arguments...})`, call `select_pytest_args(repo_root=ctx.repo_root, paths=..., marker=..., keyword=..., adapters=...)`. If it returns no path, marker or keyword, the run is the whole suite: refuse with `DevGuardError("name at least one path, marker or keyword; the whole suite is `just test`")`.
3. Build the child environment with `ctx.child_env(extra)`. When `adapters` is given and contains `postgres`, or the marker is `parity` or `requires_postgres`, add `TL_REQUIRE_POSTGRES=1`. If the child environment has `TL_PG_URL`, call `resolve_postgres` on it first (a database outside the dev rule makes the whole call a refusal).
4. Run `[sys.executable, "-m", "pytest", *args]` with `subprocess.Popen(..., cwd=ctx.repo_root, env=env, stdout=PIPE, stderr=STDOUT, text=True, start_new_session=True)` and `communicate(timeout=timeout_s)`. On `TimeoutExpired` kill the whole process group (`os.killpg(proc.pid, signal.SIGKILL)`), collect what it printed, and report `timed_out=True` (this is a result, not an error).
5. Store the report: create `ctx.reports_dir` if missing; write `<UTC YYYYMMDDTHHMMSSZ>-<6 hex chars>.txt` holding the command line (`python -m pytest ...`, no environment), `exit code: N`, a blank line and the output capped at 1 MiB (cut from the front, keep the end). Afterwards delete the oldest files in that directory so at most 50 report files remain (only files whose names match `^\d{8}T\d{6}Z-[0-9a-f]{6}\.txt$`).
6. Result model `RunTestsOutput`: `exit_code: int` (-1 when timed out), `timed_out: bool`, `passed: int | None`, `failed: int | None`, `errors: int | None`, `summary: str` (pytest's last non-empty line, at most 300 characters), `output_tail: str` (the last 6000 characters), `report: str` (the report file name only), `duration_s: float`. Parse the counts from the summary line with a regular expression (`(\d+) passed`, `(\d+) failed`, `(\d+) error`); `None` when absent.
7. Register with `@server.tool(annotations=...)` as the pattern does; the docstring lists the allowed markers and adapters, the limits and an example call.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_dev_run_tests.py -q
uv run pytest packages/tl-mcp -q
```
Expected: all pass; `just check` clean.

## Tests to add
`packages/tl-mcp/tests/test_dev_run_tests.py`. Tests that run pytest build a small repository in `tmp_path` (`tmp_path / "repo"` with `AGENTS.md`, `justfile` (any text), `dev/`, and `tests/test_ok.py`, `tests/test_fail.py`, `tests/test_slow.py` written by the test), then `DevHarness.build(tmp_path, repo_root=repo)`. The child pytest then runs inside that small repository.
- A passing file: `paths=["tests/test_ok.py"]` gives `exit_code == 0`, `passed == 2` (two tests in the file), `failed is None or 0`, a `report` that exists in `repo/dev/data/test-reports/` and contains the command line and `exit code: 0`.
- A failing test: exit code 1, `failed == 1`, `output_tail` names the failing test.
- `keyword="not slow"` deselects a test named `test_slow_one`; `marker="parity"` runs only tests marked `parity` (the small repo's `tests/conftest.py` registers the markers `parity` and `requires_postgres`, so no unknown-marker warning).
- A timeout: `tests/test_slow.py` sleeps 30 s; `timeout_s=1` returns `timed_out is True`, `exit_code == -1`, quickly (under 10 s), and no child process of that run is left (check `os.killpg` effect by asserting the call returns and a second call works).
- Refusals (each raises `ToolError` matching `refused`, and the audit file records `refused`): a path outside the allow-list (`"../etc"`, `"/etc/passwd"`, `"--co"`), a marker `"slow"`, a keyword `"a; rm -rf /"`, no filter at all, more than 20 paths (rejected by the schema: also a `ToolError`).
- A `TL_PG_URL` outside the dev rule in `ctx.environ` (build the harness context with `dataclasses.replace(env.ctx, environ={"PATH": ..., "TL_PG_URL": "postgresql://u:p@db.example.com/prod"})` and rebuild the server with `tl_mcp.dev.server.build_dev_server`) makes a `marker="parity"` call a refusal.
- The child never sees the server's secrets: set `environ={..., "SECRET_TOKEN": "x"}`; a test in the small repo that asserts `"SECRET_TOKEN" not in os.environ` passes, and `TL_ENV` is `dev` in the child.
- Report pruning: create 55 matching files, run once, at most 50 remain, and a file not matching the pattern is untouched.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Paste the output of the three acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if a refusal you need is not something `select_pytest_args` or `resolve_postgres` gives you, or if the tool would need to change a guard file.
- Stop if killing the process group is not possible in the test environment (report what you saw).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
