# P0-I8-T43 — Dev MCP tool `seed`

Status: merged
Tier: haiku
Labels: mcp, tests
Depends on: P0-I8-S41 (merged into the base of this branch)
Branch: `p0/i8c-t43-dev-seed`

## Goal
The dev MCP server has a `seed` tool that fills the dev ledger with a synthetic project by running the same script `just seed` runs (`dev/seed/seed.sh`, which starts a short-lived API on a free loopback port and plays the simulator through it), without a shell, and returns what was seeded.

## Brief references (pasted)
> **Brief 25.3 Dev/ops MCP server:** A development MCP server (local and CI only, never pointed at production data) exposes:
> - **Resources:** schema graph, event catalog, module specs, ADRs, runbooks, sample payloads, TUI screen snapshots, test reports.
> - **Tools:** run tests (filtered), run codegen and report drift, query the dev database, replay or rebuild projections, generate seed data, render a TUI screen to an SVG snapshot, send test webhooks, ...
>
> Coding agents can then inspect the running system, not just the source.
>
> **Decision D12 (fanout P0-I8):** The dev MCP server is a separate entrypoint, `python -m tl_mcp.dev`, on stdio only. It refuses any database that is not a SQLite file under the repo's `dev/` or a temp directory, or a Postgres URL whose database name starts with `tl_test` or `tl_dev`. `query_db` is read-only. `run_tests` takes a marker or path filter from an allow-list, with no shell. `send_test_webhook` only targets loopback receivers.

> **Brief 25.2:** Synthetic project generator: realistic, deterministic seed data at configurable scale, for tests, demos, and performance work. (`just seed [scale]`; scales `xs` = 3 working days, `s` = 10, `m` = 30.)

### Facts the supervisor measured (2026-10-10)
Running `TL_DB=<file> TL_API_URL=http://127.0.0.1:<port> TL_TOKENS=<file> TL_SIM_DIR=<dir> bash dev/seed/seed.sh xs` from the repository root takes about 14 s and prints, among other lines:
```
initialised /tmp/tmp.ZJ9pwkAHRY/x.db
no API at http://127.0.0.1:8799: starting one on the dev ledger
run r703d81
scope project:sim-r703d81
seeded 8 records
played 2026-11-02
played 2026-11-03
played 2026-11-04
ground truth +102 (116 lines)
ok: 530 checks
```
The script starts the API with `setsid` (its own session), stops it again in an `EXIT` trap, and needs `uv` and `bash` on `PATH` (the child environment from `ctx.child_env()` has `PATH` and `HOME`). It writes the token file and the simulator run directory where `TL_TOKENS` and `TL_SIM_DIR` say.

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
- `packages/tl-mcp/src/tl_mcp/dev/tool_seed.py` (the stub you replace)
- `packages/tl-mcp/src/tl_mcp/dev/tool_query_db.py` (the pattern)
- `packages/tl-mcp/src/tl_mcp/dev/runtime.py`
- `dev/seed/seed.sh`
- `packages/tl-mcp/tests/dev_harness.py`
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/dev/tool_seed.py` (replace the stub)
- `packages/tl-mcp/tests/test_dev_seed.py` (create)

## Steps
1. Tool `seed(scale: Literal["xs", "s", "m"] = "xs", timeout_s: int = 600)` with `timeout_s` bounded `ge=1, le=1800`. Annotation `ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)`.
2. Inside `guarded(ctx, "seed", {"scale": scale})`: refuse (`DevGuardError`) unless `ctx.target.kind == "sqlite"` ("seed needs a SQLite dev database"); raise `DevToolFailure("dev/seed/seed.sh is missing")` if `ctx.repo_root / "dev/seed/seed.sh"` is not a file.
3. Pick a free loopback port: bind a socket to `("127.0.0.1", 0)`, read the port, close it. Build the extra environment: `TL_DB` = the target file, `TL_API_URL` = `http://127.0.0.1:<port>`, `TL_TOKENS` = `<target dir>/seed-tokens.json`, `TL_SIM_DIR` = `<target dir>/sim` (next to the database, so a temporary database leaves nothing in `dev/data`).
4. Run `["bash", "<repo>/dev/seed/seed.sh", scale]` with `subprocess.Popen(..., cwd=ctx.repo_root, env=ctx.child_env(extra), stdout=PIPE, stderr=STDOUT, text=True, start_new_session=True)` and `communicate(timeout=timeout_s)`. On `TimeoutExpired`: `os.killpg(proc.pid, signal.SIGTERM)` first (the script's `EXIT` trap stops the API it started), `communicate(timeout=10)`, and if that also times out `os.killpg(proc.pid, signal.SIGKILL)`. A timeout is a result (`timed_out=True`), not an error.
5. Result model `SeedOutput`: `ok: bool` (exit code 0 and not timed out), `scale: str`, `exit_code: int` (-1 if timed out), `timed_out: bool`, `run: str | None` (from the line `run <id>`), `scope: str | None` (from `scope <scope>`), `records: int | None` (from `seeded <n> records`), `api_port: int`, `output_tail: str` (the last 4000 characters), `duration_s: float`. Parse with regular expressions anchored to line starts.
6. The docstring says that it seeds the dev ledger through the API, that a second call adds a second simulated project, the three scales and their rough cost (`xs` about 15 s).

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_dev_seed.py -q
uv run pytest packages/tl-mcp -q
```
Expected: all pass (the `xs` seed test takes about 15 s).

## Tests to add
`packages/tl-mcp/tests/test_dev_seed.py` (use `DevHarness.build(tmp_path)`, which gives a real repository root and a temporary database):
- `seed(scale="xs")` returns `ok is True`, a `run` and `scope` (`project:sim-...`), `records > 0`; then `query_db` (`SELECT count(*) FROM cur_core_record WHERE scope = '<scope>'`) agrees with `records` or exceeds it; the audit file records `ok`; the files `seed-tokens.json` and `sim/` are in `tmp_path`, and `git status --porcelain` of the repository shows nothing new from this test.
- After the call no API answers on `api_port` (connect to `127.0.0.1:<api_port>` is refused; allow up to 5 s of retries).
- A timeout: `timeout_s=1` returns `timed_out is True`, `ok is False`, `exit_code == -1`, and the port is free again within 15 s.
- A Postgres target (use the `dev_pg_target` fixture if the T42 branch has been merged; otherwise `resolve_target("postgresql://postgres:x@localhost/tl_test", repo_root=...)`, which needs no server) raises `ToolError` matching `refused`.
- A repository root without `dev/seed/seed.sh` (a `tmp_path / "repo"` with `AGENTS.md`, `justfile`, `dev/`) raises `ToolError` matching `seed.sh`.
- `scale="l"` and `timeout_s=0` are rejected by the schema (`ToolError`).
- The child environment holds none of the server's other variables: assert through a patched `Popen` wrapper or by building the context with `environ={"PATH": ..., "HOME": ..., "SECRET": "x"}` and checking `ctx.child_env` (unit-level) that `SECRET` is absent and `TL_ENV == "dev"`.

## Report requirements
Standard report. Paste the output of the three acceptance commands and the wall time of the seed test.

## Escalation triggers
- Stop and report *Blocked* if `seed.sh` needs a variable the steps do not list, or if the seed leaves a process running after the tool returns.
- Stop if `uv` is not on `PATH` in the test environment.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
