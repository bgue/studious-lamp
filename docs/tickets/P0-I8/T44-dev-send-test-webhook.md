# P0-I8-T44 — Dev MCP tool `send_test_webhook`

Status: merged
Tier: haiku
Labels: mcp, tests
Depends on: P0-I8-S41 (merged into the base of this branch)
Branch: `p0/i8c-t44-dev-send-test-webhook`

## Goal
The dev MCP server has a `send_test_webhook` tool: it sends one signed catalog sample event to a receiver on this machine (loopback only), the way a real delivery is signed, and reports the answer. It needs no subscription and writes nothing to the ledger.

## Brief references (pasted)
> **Brief 25.3 Dev/ops MCP server:** A development MCP server (local and CI only, never pointed at production data) exposes:
> - **Resources:** schema graph, event catalog, module specs, ADRs, runbooks, sample payloads, TUI screen snapshots, test reports.
> - **Tools:** run tests (filtered), run codegen and report drift, query the dev database, replay or rebuild projections, generate seed data, render a TUI screen to an SVG snapshot, send test webhooks, ...
>
> Coding agents can then inspect the running system, not just the source.
>
> **Decision D12 (fanout P0-I8):** The dev MCP server is a separate entrypoint, `python -m tl_mcp.dev`, on stdio only. It refuses any database that is not a SQLite file under the repo's `dev/` or a temp directory, or a Postgres URL whose database name starts with `tl_test` or `tl_dev`. `query_db` is read-only. `run_tests` takes a marker or path filter from an allow-list, with no shell. `send_test_webhook` only targets loopback receivers.

> **Brief 18.4 / event catalog:** webhooks carry CloudEvents 1.0 JSON signed with Standard Webhooks headers (`webhook-id`, `webhook-timestamp`, `webhook-signature` = `v1,<base64 HMAC-SHA256 of "<id>.<timestamp>.<body>">`, one entry per active secret). A request sent as a test carries the extra header `webhook-test: 1`; real deliveries never do. Receivers dedupe on the event `id`.

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-mcp/src/tl_mcp/dev/guard.py
@dataclass(frozen=True)
class LoopbackUrl:
    """A webhook target that is this machine, resolved without DNS."""

    scheme: str
    ip: str
    port: int
    path_and_query: str

def check_loopback_url(url: str) -> LoopbackUrl:
    """``url`` as a loopback target, or :class:`DevGuardError`. (localhost or a literal loopback address only)"""
```
```python
# packages/tl-core/src/tl_core/webhooks/signing.py
def generate_secret() -> str: ...                      # "whsec_" + base64 of 32 random bytes
class SigningSecret:                                   # SigningSecret(value: str); validates the form
def sign_headers(message_id: str, timestamp: int, body: str, secrets: Iterable[SigningSecret]) -> dict[str, str]: ...
def verify(headers, body, secrets, *, now=None, tolerance_s=300) -> str: ...   # raises SignatureError
```
```python
# packages/tl-core/src/tl_core/webhooks/egress.py
@dataclass(frozen=True)
class ResolvedTarget:
    scheme: Literal["http", "https"]
    host: str
    port: int
    ip: str
    path_and_query: str
```
```python
# packages/tl-core/src/tl_core/webhooks/transport.py
class HttpxTransport:        # follow_redirects=False, trust_env=False (ignores proxy variables)
    def send(self, target: ResolvedTarget, headers: dict[str, str], body: bytes, *, timeout_s: float) -> TransportResult: ...
class TransportResult:       # status: int | None, latency_ms: int, excerpt: str = "", error: str | None = None, ok property
```
```python
# packages/tl-schema/src/tl_schema/catalog.py
def event_types() -> list[str]: ...
def sample(event_type: str) -> dict[str, Any]:   # {"payload": ..., "envelope": <CloudEvent>}
```
```python
# packages/tl-core/src/tl_core/webhooks/delivery.py  (what the real "send a test" does, for reference; do not import the engine)
envelope = dict(sample(event_type)["envelope"])
envelope["id"] = new_ulid()
envelope["time"] = iso_z(now)
body = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
headers = {
    **sign_headers(claim.event_id, int(started.timestamp()), claim.body, claim.secrets),
    "Content-Type": "application/json",
    "webhook-test": "1",
}
```
`new_ulid` is `tl_core.util.new_ulid`; `iso_z` is `tl_core.webhooks.base.iso_z`; `utc_now` is in the same module.
`tl_core.webhooks.receiver.DevReceiver(secrets=[...])` is a loopback receiver for tests: `with DevReceiver([secret]) as r:` gives `r.url`, `r.messages()` (each with `.verified`, `.headers` lower-cased, `.body`), `r.rejected()`.

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
- `packages/tl-mcp/src/tl_mcp/dev/tool_webhook.py` (the stub you replace)
- `packages/tl-mcp/src/tl_mcp/dev/tool_query_db.py` (the pattern)
- `packages/tl-mcp/src/tl_mcp/dev/guard.py` (read `check_loopback_url` and `LoopbackUrl` only)
- `packages/tl-core/src/tl_core/webhooks/receiver.py` (for the tests)
- `packages/tl-mcp/tests/dev_harness.py`
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/dev/tool_webhook.py` (replace the stub)
- `packages/tl-mcp/tests/test_dev_webhook.py` (create)

## Steps
1. Tool `send_test_webhook(url: str, event_type: str = "Record.Created", secret: str | None = None, timeout_s: int = 5)`: `url` `max_length=2048`, `event_type` `max_length=80`, `secret` `max_length=200`, `timeout_s` `ge=1, le=10`. Annotation `ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)`.
2. Inside `guarded(ctx, "send_test_webhook", {"url": url, "event_type": event_type})` (never put the secret in the audit detail): `target = check_loopback_url(url)` first, before anything else is built; then check `event_type in catalog.event_types()` (else `ValueError` naming the first 5 valid types). `secret=None` means a fresh secret from `generate_secret()`; a given secret goes through `SigningSecret(...)`, whose `ValueError` is the refusal text.
3. Build the body and headers exactly as the reference above does (fresh ULID event id, current time, sorted compact JSON), with `ResolvedTarget(scheme=target.scheme, host=target.ip, port=target.port, ip=target.ip, path_and_query=target.path_and_query)` and `HttpxTransport().send(resolved, headers, body.encode("utf-8"), timeout_s=float(timeout_s))`. Connect to the literal IP; never resolve a name.
4. Result model `WebhookTestOutput`: `ok: bool` (`TransportResult.ok`), `status: int | None`, `latency_ms: int`, `error: str | None`, `excerpt: str` (the receiver's answer, at most 512 characters), `event_id: str`, `event_type: str`, `target: str` (`"<ip>:<port>"`), `secret: str | None` (set only when the tool generated one, so the caller can configure its receiver; never echo a secret the caller passed), `header: str = "webhook-test: 1"`.
5. A receiver that is down is a result (`ok False`, `error` from the transport, `status None`), not an exception.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_dev_webhook.py -q
uv run pytest packages/tl-mcp -q
```
Expected: all pass.

## Tests to add
`packages/tl-mcp/tests/test_dev_webhook.py` (use the `dev_env` fixture; receivers are `DevReceiver` in the test):
- Delivery: with `secret = generate_secret()` and `with DevReceiver([secret]) as r:`, `send_test_webhook(url=r.url, secret=secret)` returns `ok True`, `status 200`, `secret is None` (a given secret is not echoed); `r.messages()` has one entry with `verified True`, header `webhook-test` equal to `"1"`, and a body that parses to a CloudEvent whose `type` ends with `.Record.Created.v1` and whose `id` equals the output's `event_id`.
- Generated secret: `secret=None` returns a `whsec_` secret and `verify(received.headers, received.body, [SigningSecret(out.secret)])` succeeds against what the receiver got (start the receiver with an unrelated secret: it rejects with `verified False`, but `r.rejected()` holds the message to verify).
- A wrong secret is rejected by the receiver: `ok` is whatever the receiver's status says (not 2xx), and the output still carries the status.
- Another event type from the catalog (`Link.Added`) is sent; an unknown one (`Nope.Created`) raises `ToolError`.
- Refused targets, parametrized (`http://example.com/h`, `http://10.0.0.1/h`, `http://169.254.169.254/`, `http://2130706433/`, `http://127.0.0.1.nip.io/`, `http://user:pw@127.0.0.1/`, `ftp://127.0.0.1/`, `file:///etc/passwd`): each raises `ToolError` matching `refused`, and the audit file holds a `refused` record for it. A real receiver is running on 127.0.0.1 during these calls and has received nothing at the end.
- A malformed secret (`"abc"`) raises `ToolError`.
- A redirect is not followed: a throw-away `http.server` thread on 127.0.0.1 answers 302 with `Location: http://example.com/` and counts requests; the tool returns `status 302`, `ok False`, and the server saw exactly one request.
- Proxy variables are ignored: `monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")` and `HTTPS_PROXY` do not stop delivery to the receiver.
- A receiver that is not listening (a port that was just closed) returns `ok False`, `status None`, `error` not empty, within 3 s.
- A slow receiver (`http.server` that sleeps 5 s) with `timeout_s=1` returns `ok False` with a timeout `error` in under 4 s.
- The audit record of a successful call holds the URL and the event type and no secret (search the whole audit file for the secret string).

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if `check_loopback_url` refuses a URL the tests need accepted, or accepts one they need refused (the guard is the supervisor's).
- Stop if `HttpxTransport` follows redirects or reads proxy variables at the branch point.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
