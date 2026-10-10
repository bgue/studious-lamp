# P0-I8-T41 — Dev MCP tool `gen` (codegen drift report)

Status: ready
Tier: haiku
Labels: mcp, tests
Depends on: P0-I8-S41 (merged into the base of this branch)
Branch: `p0/i8c-t41-dev-gen`

## Goal
The dev MCP server has a `gen` tool that runs the schema generators in memory and reports codegen drift: which committed generated files are missing, differ or are stale, with a short unified diff of the differing ones. With `apply=true` it regenerates the files (what `just gen` does) and reports again.

## Brief references (pasted)
> **Brief 25.3 Dev/ops MCP server:** A development MCP server (local and CI only, never pointed at production data) exposes:
> - **Resources:** schema graph, event catalog, module specs, ADRs, runbooks, sample payloads, TUI screen snapshots, test reports.
> - **Tools:** run tests (filtered), run codegen and report drift, query the dev database, replay or rebuild projections, generate seed data, render a TUI screen to an SVG snapshot, send test webhooks, ...
>
> Coding agents can then inspect the running system, not just the source.
>
> **Decision D12 (fanout P0-I8):** The dev MCP server is a separate entrypoint, `python -m tl_mcp.dev`, on stdio only. It refuses any database that is not a SQLite file under the repo's `dev/` or a temp directory, or a Postgres URL whose database name starts with `tl_test` or `tl_dev`. `query_db` is read-only. `run_tests` takes a marker or path filter from an allow-list, with no shell. `send_test_webhook` only targets loopback receivers.

> **Brief 25.4:** Codegen drift check: generated artefacts match the schema. `just check` fails if `just gen` produces a diff (build spec 03 section 4). Generated artefacts live only under `packages/tl-schema/src/tl_schema/generated/` and are never edited by hand.

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-schema/src/tl_schema/generate.py  (the functions you call)
GENERATED_DIR: Path = Path(__file__).resolve().parent / "generated"
SCHEMA_DIR: Path = Path(__file__).resolve().parents[4] / "schema" / "core"

def outputs(schema_dir: Path = SCHEMA_DIR) -> dict[str, str]:
    """Run every generator. Keys are posix paths relative to generated/, sorted."""

def problems(out_dir: Path, files: dict[str, str]) -> list[str]:
    """Return lines 'missing: <path>', 'differs: <path>', 'stale: <path>'.

    A stale line is a file on disk that is not in files. An empty list means in sync.
    """

def write(out_dir: Path, files: dict[str, str]) -> None:
    """Delete stale files, create parent directories, write every file as UTF-8."""
```

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
- `packages/tl-mcp/src/tl_mcp/dev/tool_gen.py` (the stub you replace)
- `packages/tl-mcp/src/tl_mcp/dev/tool_query_db.py` (the pattern)
- `packages/tl-schema/src/tl_schema/generate.py`
- `packages/tl-mcp/src/tl_mcp/dev/runtime.py`
- `packages/tl-mcp/tests/dev_harness.py`
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/dev/tool_gen.py` (replace the stub)
- `packages/tl-mcp/tests/test_dev_gen.py` (create)

## Steps
1. Write a plain function `gen_report(schema_dir: Path, out_dir: Path, *, apply: bool) -> GenOutput` that calls `outputs(schema_dir)` and `problems(out_dir, files)`. If `apply` and there are problems, call `write(out_dir, files)` and compute `problems` again. Model `GenOutput`: `in_sync: bool` (no problems after any apply), `file_count: int` (the number of generated files), `drift: list[DriftItem]` (`path: str`, `kind: Literal["missing", "differs", "stale"]`; parse the `problems` lines `kind: path`), `diff: str` (unified diff, via `difflib.unified_diff`, of at most 5 differing files: current text against what the generators produce, file labels `a/<path>` and `b/<path>`, the whole string capped at 20000 characters with `... (cut)` at the end), `applied: bool`.
2. The tool `gen(apply: bool = False)` calls `gen_report(ctx.repo_root / "schema" / "core", ctx.repo_root / "packages" / "tl-schema" / "src" / "tl_schema" / "generated", apply=apply)` inside `guarded(ctx, "gen", {"apply": apply})`. Before it writes (`apply=True`), check that `out_dir` is inside `ctx.repo_root` after `resolve()`; otherwise raise `DevGuardError`.
3. Annotate the tool `ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)`; the docstring says that without `apply` nothing is written and what `apply` does.
4. Do not import `tl_schema.generate` at module top level if that makes `tl_mcp.dev.server` slower to start than 1 s; a local import inside the function is fine.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_dev_gen.py -q
uv run pytest packages/tl-mcp -q
```
Expected: all pass; `just check` clean.

## Tests to add
`packages/tl-mcp/tests/test_dev_gen.py`:
- The real repository is in sync: `env.structured("gen")` gives `in_sync is True`, `drift == []`, `applied is False`, `file_count > 50`.
- Drift is reported: copy `packages/tl-schema/src/tl_schema/generated` to `tmp_path / "generated"` with `shutil.copytree`, then (a) edit one file, (b) delete one file, (c) add a file `extra.txt`. `gen_report(SCHEMA_DIR, copy, apply=False)` returns three drift items with kinds `differs`, `missing`, `stale`, `in_sync is False`, a `diff` that contains `--- a/<edited path>` and the changed line, and the copy is unchanged (nothing written).
- `apply=True` on the copy rewrites it: afterwards `in_sync is True`, `applied is True`, and the copy equals the real generated directory (compare file names and bytes).
- The diff is capped: a copy where 10 files were edited shows at most 5 files in `diff` and `len(diff) <= 20000 + 20`.
- Through the server: `env.call("gen", apply=False)` is audited as `ok`; `git status --porcelain packages/tl-schema` is empty after the whole test module (the tool did not touch the real tree when `apply` is false).

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if `tl_schema.generate` has no function with the signature above.
- Stop if the real repository is reported as drifting at the branch point (that is a bug elsewhere; say so).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
