# P0-I8-T46 — Dev MCP resources: schema graph and event catalog

Status: in-review
Tier: haiku
Labels: mcp, tests
Depends on: P0-I8-S41 (merged into the base of this branch)
Branch: `p0/i8c-t46-dev-resources-schema`

## Goal
The dev MCP server serves the schema graph of the core LinkML schema and the event catalog (the generated page, its index and one sample payload per event type) as resources, so a coding agent can read the shape of the system without opening generated files.

## Brief references (pasted)
> **Brief 25.3 Dev/ops MCP server:** A development MCP server (local and CI only, never pointed at production data) exposes:
> - **Resources:** schema graph, event catalog, module specs, ADRs, runbooks, sample payloads, TUI screen snapshots, test reports.
> - **Tools:** run tests (filtered), run codegen and report drift, query the dev database, replay or rebuild projections, generate seed data, render a TUI screen to an SVG snapshot, send test webhooks, ...
>
> Coding agents can then inspect the running system, not just the source.
>
> **Decision D12 (fanout P0-I8):** The dev MCP server is a separate entrypoint, `python -m tl_mcp.dev`, on stdio only. It refuses any database that is not a SQLite file under the repo's `dev/` or a temp directory, or a Postgres URL whose database name starts with `tl_test` or `tl_dev`. `query_db` is read-only. `run_tests` takes a marker or path filter from an allow-list, with no shell. `send_test_webhook` only targets loopback receivers.

> **Brief 25.1:** most surfaces are generated from LinkML, so adding a record type is mainly a schema and workflow change. **Event catalog:** every ledger event type that can reach a webhook subscriber, generated from the LinkML event classes, committed under `packages/tl-schema/src/tl_schema/generated/` (`catalog/index.json`, `catalog/samples/<Event>.v1.json`, `docs/event-catalog.md`).

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-schema/src/tl_schema/catalog.py
def index() -> list[dict[str, Any]]:
    """The catalog entries in event-type order (``event_type``, ``ce_type``, ``schema``, ...)."""
def event_types() -> list[str]: ...
def sample(event_type: str) -> dict[str, Any]:
    """``{"payload": <ledger payload>, "envelope": <delta-mode CloudEvent>}`` for ``event_type``."""
    # raises KeyError for an unknown event type
```
```python
# packages/tl-mcp/src/tl_mcp/dev/guard.py
def safe_child(directory: Path, name: str, suffixes: Sequence[str]) -> Path:
    """The file ``name`` directly inside ``directory``, or DevGuardError (plain names only)."""
```
LinkML (already installed) for the graph:
```python
from linkml_runtime.utils.schemaview import SchemaView
view = SchemaView(str(core_yaml))          # an absolute path; do NOT change the working directory
view.all_classes()                         # {name: ClassDefinition}
view.get_class(name)                       # .is_a, .mixins, .abstract, .description, .annotations
view.class_induced_slots(name)             # slots with .name, .range, .required, .multivalued
view.all_enums()                           # {name: EnumDefinition}; .permissible_values
```
A class is a current-state class when its annotations hold `tl:current_state` with a true value (`str(definition.annotations["tl:current_state"].value).lower() == "true"` when the key is present).

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
@server.resource("tl://dev/event-sample/{event_type}", name="event_sample", title="...", description="...", mime_type="application/json")
def event_sample(event_type: str) -> str:
    with guarded(ctx, "resource.event_sample", {"event_type": event_type}, error=ResourceError):
        ...
```
(`from mcp.server.mcpserver.exceptions import ResourceError`; `guarded(..., error=ResourceError)` maps refusals to `ResourceError`.)

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/dev/resources_schema.py` (the stub you replace)
- `packages/tl-mcp/src/tl_mcp/resources.py` (the product server's resource bodies: the `dump` helper and style)
- `packages/tl-schema/src/tl_schema/catalog.py`
- `packages/tl-mcp/src/tl_mcp/dev/runtime.py`
- `packages/tl-mcp/tests/dev_harness.py`
may explore: `schema/core/record.yaml` (to see a class and its annotations)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/dev/resources_schema.py` (replace the stub)
- `packages/tl-mcp/tests/test_dev_resources_schema.py` (create)

## Steps
1. Register four resources (all read-only, no tool):
   - `tl://dev/event-catalog` (`text/markdown`): the text of `<repo>/packages/tl-schema/src/tl_schema/generated/docs/event-catalog.md`, found with `safe_child`.
   - `tl://dev/event-catalog/index` (`application/json`): `catalog.index()` as compact sorted JSON.
   - `tl://dev/event-sample/{event_type}` (`application/json`): `catalog.sample(event_type)`; check `event_type` is non-empty, at most 80 characters and in `catalog.event_types()`; otherwise `ResourceError` naming the first 5 valid types.
   - `tl://dev/schema-graph` (`application/json`): the graph below.
2. Graph shape, deterministic (everything sorted by name, `json.dumps(..., sort_keys=True, separators=(",", ":"))`):
   ```json
   {"schema": "tl_core",
    "classes": [{"name": "Record", "is_a": "RecordEnvelope", "mixins": [], "abstract": false,
                 "current_state": true, "description": "<first sentence, at most 200 characters>",
                 "slots": [{"name": "id", "range": "Ulid", "required": true, "multivalued": false}]}],
    "enums": [{"name": "ConformanceStatus", "values": ["nonconformant", "ok", "waived", "warning"]}],
    "edges": [{"from": "Record", "to": "RecordEnvelope", "kind": "is_a", "slot": null},
              {"from": "RecordEnvelope", "to": "ConformanceStatus", "kind": "range", "slot": "conformance"}]}
   ```
   `edges` has one `is_a` edge per class with a parent, one `mixin` edge per mixin, and one `range` edge per slot whose range is a class or an enum of the schema (not for built-in types such as `string`). Build the `SchemaView` from `<repo>/schema/core/core.yaml`.
3. Cache nothing across calls except what is cheap to rebuild; reading the graph may take about a second.
4. Every body runs inside `guarded(ctx, "resource.<name>", {...}, error=ResourceError)`. No absolute path appears in any returned text.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_dev_resources_schema.py -q
uv run pytest packages/tl-mcp -q
```
Expected: all pass.

## Tests to add
`packages/tl-mcp/tests/test_dev_resources_schema.py` (use the `dev_env` fixture and `env.read(uri)`):
- `env.resource_uris()` includes the four URIs (the template appears with its `{event_type}` placeholder).
- The catalog page equals the committed file's text; the index parses and its `event_type` list equals `tl_schema.catalog.event_types()`.
- A sample for `Record.Created` parses and has the keys `payload` and `envelope`; an unknown type (`Nope.Created`), an empty string and a 200-character string raise `ResourceError`.
- The graph: has a class `Record` with `is_a == "RecordEnvelope"`, `current_state is True`, and an `id` slot with `required is True`; has an enum `ConformanceStatus` whose values are sorted; has the edge `{"from": "Record", "to": "RecordEnvelope", "kind": "is_a", "slot": null}`; every edge endpoint is a class or enum name in the document; two reads are byte-identical.
- No resource text contains the repository's absolute path (`str(find_repo_root())`).
- The working directory is unchanged by a read of the graph (compare `os.getcwd()` before and after).

## Report requirements
Standard report. Paste the output of the three acceptance commands and the size in bytes of each resource.

## Escalation triggers
- Stop and report *Blocked* if `SchemaView` needs the working directory to be `schema/core` to load the schema (say what error you saw).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
