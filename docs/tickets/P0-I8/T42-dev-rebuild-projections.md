# P0-I8-T42 — Dev MCP tool `rebuild_projections`

Status: ready
Tier: haiku
Labels: mcp, tests
Depends on: P0-I8-S41 (merged into the base of this branch)
Branch: `p0/i8c-t42-dev-rebuild-projections`

## Goal
The dev MCP server has a `rebuild_projections` tool: it resets the named projectors (default: all) of the dev database and replays the ledger into them, in one transaction, on SQLite or on a dev Postgres. It returns how many events were replayed.

## Brief references (pasted)
> **Brief 25.3 Dev/ops MCP server:** A development MCP server (local and CI only, never pointed at production data) exposes:
> - **Resources:** schema graph, event catalog, module specs, ADRs, runbooks, sample payloads, TUI screen snapshots, test reports.
> - **Tools:** run tests (filtered), run codegen and report drift, query the dev database, replay or rebuild projections, generate seed data, render a TUI screen to an SVG snapshot, send test webhooks, ...
>
> Coding agents can then inspect the running system, not just the source.
>
> **Decision D12 (fanout P0-I8):** The dev MCP server is a separate entrypoint, `python -m tl_mcp.dev`, on stdio only. It refuses any database that is not a SQLite file under the repo's `dev/` or a temp directory, or a Postgres URL whose database name starts with `tl_test` or `tl_dev`. `query_db` is read-only. `run_tests` takes a marker or path filter from an allow-list, with no shell. `send_test_webhook` only targets loopback receivers.

> **Brief 25.4 (projection determinism):** replay(events) twice gives identical projections; projections after a shadow rebuild equal the live ones. A rebuild resets projections only; the ledger is never changed (root `AGENTS.md`, rule 3).

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-adapters/src/tl_adapters/db.py
def rebuild_projections(
    target: DbTarget,
    *,
    types: Sequence[str] | None = None,
    registry: ProjectorRegistry | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Reset projectors and replay the whole ledger into them, in one transaction."""
```
`DbTarget = str | Path` (a SQLite file or a `postgresql://` URL). `ctx.target.db_arg` is exactly this value.

```python
# packages/tl-core/src/tl_core/projection/defaults.py
def default_registry() -> InMemoryRegistry:
    """A fresh registry holding the built-in projectors."""
```
Projector names today: `core_record`, `pset_values`, `links`, `numbering`, `workflow`, `files`, `webhook_subscriptions`, `webhook_state`, `proposals`, `feed`, `outbox`. (`registry.all()` yields projectors with a `.name`.)

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
- `packages/tl-mcp/src/tl_mcp/dev/tool_rebuild.py` (the stub you replace)
- `packages/tl-mcp/src/tl_mcp/dev/tool_query_db.py` (the pattern)
- `packages/tl-mcp/src/tl_mcp/dev/runtime.py`
- `packages/tl-mcp/tests/dev_harness.py`
- `packages/tl-mcp/tests/test_dev_query.py` (its `pg_target` fixture creates a throw-away Postgres schema; move that fixture into `packages/tl-mcp/tests/conftest.py` as `dev_pg_target` so both test modules share it, and change `test_dev_query.py` to use it: this is the one edit outside your own files that is allowed)
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/dev/tool_rebuild.py` (replace the stub)
- `packages/tl-mcp/tests/test_dev_rebuild.py` (create)
- `packages/tl-mcp/tests/conftest.py` (add the `dev_pg_target` fixture)
- `packages/tl-mcp/tests/test_dev_query.py` (use the moved fixture; no other change)

## Steps
1. Tool `rebuild_projections(only: list[str] | None = None)`; `only` has at most 20 items of at most 64 characters each. Annotation: `ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)`.
2. Inside `guarded(ctx, "rebuild_projections", {"only": only})`: refuse when the target is a SQLite file that does not exist (`DevGuardError` is wrong here: raise `DevToolFailure("the dev database does not exist yet: run `tl init` or the seed tool")`). Validate each name in `only` against `default_registry().all()` names; an unknown name raises `ValueError` listing the valid names (`guarded` turns it into a `ToolError`). Then call `tl_adapters.db.rebuild_projections(ctx.target.db_arg, types=only or None)`.
3. Result model `RebuildOutput`: `replayed: int`, `projectors: list[str]` (the names rebuilt, in registry order), `dialect: str` (`ctx.target.dialect`).
4. A database failure (`sqlalchemy.exc.SQLAlchemyError`) becomes `DevToolFailure(f"rebuild failed: {type(exc).__name__}")`: no driver text, no paths.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_dev_rebuild.py packages/tl-mcp/tests/test_dev_query.py -q
uv run pytest packages/tl-mcp -q
```
Expected: all pass (the Postgres tests run: native Postgres is up; if `sudo pg_ctlcluster 16 main start` is needed, run it).

## Tests to add
`packages/tl-mcp/tests/test_dev_rebuild.py`:
- SQLite: `env.create_record("K-1")`, `env.create_record("K-2")`; delete the rows of `cur_core_record` with a direct `sqlite3` connection; `rebuild_projections()` returns `replayed >= 2`, lists `core_record` among `projectors`, and `query_db` then returns both records again (compare the two keys, sorted).
- `only=["core_record"]` rebuilds just that projector (`projectors == ["core_record"]`); damage `cur_core_record` and `cur_pset_values` rows, rebuild only `core_record`: the first is restored.
- An unknown name (`["nope"]`) raises `ToolError` whose text contains `core_record` (the valid names) and changes nothing; the ledger event count (`SELECT count(*) FROM events`) is unchanged by every call (the rebuild never writes events).
- A missing SQLite database raises `ToolError` matching `does not exist` and creates no file.
- Postgres (`@pytest.mark.requires_postgres`, using `dev_pg_target`): append two records with `tl_adapters.db.open_uow(url)` (no helper exists for Postgres; use `handle_create_record` as `DevHarness.create_record` does), damage `cur_core_record` with `DELETE`, rebuild through a server built over the Postgres target (`DevHarness.build(tmp_path, target=dev_pg_target)`), and check with `query_db`.
- Every call is audited (`ok` or `error`).

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if `rebuild_projections` has a different signature at the branch point.
- Stop if the Postgres tests cannot reach the server (report `pg_isready` output).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
