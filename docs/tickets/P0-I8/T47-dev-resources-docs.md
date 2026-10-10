# P0-I8-T47 — Dev MCP resources: ADRs, runbooks and test reports

Status: in-review
Tier: haiku
Labels: mcp, tests
Depends on: P0-I8-S41 (merged into the base of this branch)
Branch: `p0/i8c-t47-dev-resources-docs`

## Goal
The dev MCP server serves the architecture decision records, the runbooks and the stored test reports as resources: an index of each and the text of one document by its plain name. A name that is not a plain file name never reaches the file system.

## Brief references (pasted)
> **Brief 25.3 Dev/ops MCP server:** A development MCP server (local and CI only, never pointed at production data) exposes:
> - **Resources:** schema graph, event catalog, module specs, ADRs, runbooks, sample payloads, TUI screen snapshots, test reports.
> - **Tools:** run tests (filtered), run codegen and report drift, query the dev database, replay or rebuild projections, generate seed data, render a TUI screen to an SVG snapshot, send test webhooks, ...
>
> Coding agents can then inspect the running system, not just the source.
>
> **Decision D12 (fanout P0-I8):** The dev MCP server is a separate entrypoint, `python -m tl_mcp.dev`, on stdio only. It refuses any database that is not a SQLite file under the repo's `dev/` or a temp directory, or a Postgres URL whose database name starts with `tl_test` or `tl_dev`. `query_db` is read-only. `run_tests` takes a marker or path filter from an allow-list, with no shell. `send_test_webhook` only targets loopback receivers.

> **Brief 25.2 / 24.6:** templates for ADRs and runbooks; every operational command has a runbook. ADRs live in `docs/adr/<nnnn>-<slug>.md` (first line `# ADR-nnnn ...`, a line `Status: accepted`), runbooks in `docs/runbooks/<slug>.md` (first line `# Runbook ...`). `run_tests` (ticket T40) stores reports as `dev/data/test-reports/<YYYYMMDDTHHMMSSZ>-<6 hex>.txt`.

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-mcp/src/tl_mcp/dev/guard.py
def safe_child(directory: Path, name: str, suffixes: Sequence[str]) -> Path:
    """The file ``name`` directly inside ``directory``, or :class:`DevGuardError`.

    ``name`` is a plain file name: no separator, no ``..``, one of ``suffixes``. The resolved path
    must still be inside ``directory`` (a symlink that leaves it is refused).
    """

def list_documents(directory: Path, suffixes: Sequence[str]) -> list[str]:
    """Names of the regular files directly inside ``directory`` that ``safe_child`` would open."""
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

Resources are registered like this in the SDK (a template parameter becomes a function argument; return the text):
```python
@server.resource("tl://dev/adr/{name}", name="adr", title="...", description="...", mime_type="text/markdown")
def adr(name: str) -> str:
    with guarded(ctx, "resource.adr", {"name": name}, error=ResourceError):
        ...
```
(`from mcp.server.mcpserver.exceptions import ResourceError`.)

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/dev/resources_docs.py` (the stub you replace)
- `packages/tl-mcp/src/tl_mcp/dev/guard.py` (read `safe_child` and `list_documents` only)
- `packages/tl-mcp/src/tl_mcp/dev/runtime.py`
- `docs/adr/0004-relay-orchestration.md` (an example ADR)
- `packages/tl-mcp/tests/dev_harness.py`
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/dev/resources_docs.py` (replace the stub)
- `packages/tl-mcp/tests/test_dev_resources_docs.py` (create)

## Steps
1. Register six resources, two per kind (`adr`, `runbook`, `test-report`):
   - `tl://dev/adrs`, `tl://dev/runbooks`, `tl://dev/test-reports` (`application/json`): an index.
   - `tl://dev/adr/{name}`, `tl://dev/runbook/{name}` (`text/markdown`), `tl://dev/test-report/{name}` (`text/plain`): one document. For ADRs and runbooks `{name}` is the file name without `.md` (`0004-relay-orchestration`); for reports it is the full file name (`20261010T120000Z-ab12cd.txt`).
2. Directories: `<repo>/docs/adr` (suffix `.md`), `<repo>/docs/runbooks` (suffix `.md`; leave out `README.md`), `ctx.reports_dir` (suffix `.txt`). Always list with `list_documents` and open with `safe_child`; never join a name into a path yourself. A `{name}` longer than 128 characters, or one `safe_child` refuses, is a `ResourceError("no such document")` with no path in the text.
3. Index entry for an ADR or runbook: `{"name": ..., "title": <text of the first line starting with "# ", without the hashes, or the name>, "status": <the text after "Status:" on the first line that starts with it, else null>}`, sorted by name. For reports: `{"name": <file name>, "bytes": <size>}`, newest first (sort by name descending, which is time order), at most 100 entries.
4. A document is read as UTF-8 with `errors="replace"` and cut to 1 MiB (the cut text ends with `\n... (cut)\n`).
5. Every body runs inside `guarded(ctx, "resource.<name>", {...}, error=ResourceError)`.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_dev_resources_docs.py -q
uv run pytest packages/tl-mcp -q
```
Expected: all pass.

## Tests to add
`packages/tl-mcp/tests/test_dev_resources_docs.py` (use the real repository for ADRs and runbooks via the `dev_env` fixture, and a small copy tree for reports and for cut/traversal cases: `DevHarness.build(tmp_path, repo_root=tmp_path / "repo")` with `repo/docs/adr`, `repo/docs/runbooks`, `repo/dev/data/test-reports` created by the test, plus `AGENTS.md` and `justfile` files):
- All six URIs are listed (templates with `{name}`).
- Real repository: the ADR index contains `0004-relay-orchestration` with status `accepted` and a title containing `Relay orchestration`; reading it returns the file's text; the runbook index contains `dev-mcp` only after S45, so assert instead that it contains `tui-dev` and not `README`.
- Small tree: an ADR with no `Status:` line has `status null`; a title falls back to the name when there is no heading; index order is sorted; reports are newest first and `bytes` is right.
- Traversal and odd names all raise `ResourceError` and never read outside: `../../etc/passwd`, `..`, `a/b`, `.hidden`, `x\x00y`, a 200-character name, a name for a directory, `0004-relay-orchestration.md` with the suffix included (not found; names have no suffix), and a symlink inside `docs/adr` that points to a file outside it.
- A document larger than 1 MiB is cut and ends with `... (cut)`.
- A missing reports directory gives an empty index, not an error.
- Error texts and index/document texts contain no absolute path (`str(tmp_path)` is not in any of them).

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if `safe_child` refuses a file name that the tests need served (for example a runbook name with a dot), or accepts one they need refused.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
