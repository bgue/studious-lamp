# Increment plan — P0-I4 workstream C: REST API, SSE stream, MCP read server, HTTP client

Status: in-progress
Supervisor session: 2026-10-09
Brief sections: §4, §5.3, §7.5, §10.2, §11, §18.1–§18.3, §19.1, §20
Branch: `p0/i4c` (integration branch `p0/i4`; trunk `claude/wizardly-allen-m2v96s`). Ticket branches `p0/i4c-t<nn>-<slug>`. Fanout: `docs/tickets/P0-I4/FANOUT.md`.

## Objective
Records, links, workflow, files and the change feed are reachable over HTTP and MCP with the same services the TUI uses. `tl_api` is a
FastAPI app (`create_app(backend, ...)`): record reads with the shared query language, link/trace/workflow/schema reads, a command endpoint
generated from the shared command models, an event pager, an SSE stream that resumes from `Last-Event-ID`, file routes over the WS-B file
service, and a committed, drift-checked OpenAPI document. `tl_mcp` is an MCP server with read tools (`search_records`, `get_record`,
`get_links`, `trace`) and resources. `tl_api.client.ApiClient` is a thin HTTP client that WS-D wraps as the remote `ClientInterface`.
Phase 0 identity is the dev-only stub of ADR-0005. Out of scope: any role or permission model, MCP write tools (P0-I6), WebSocket,
webhooks (P0-I5), Postgres execution (P0-I5), resumable multipart uploads, presigned download URLs through the API.

## Orchestrator decisions (binding)
- **O1** Identity follows ADR-0005: static dev tokens in `dev/data/tokens.json`; an allow-all `authorize(actor, action, resource)` hook that every route calls; loopback-only bind unless `--insecure-dev`; the actor comes from the token. No roles or permissions are designed here (human gate).
- **O2** Downloads send `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff` (the content type is client-declared). A quarantined file is never served to anyone but its uploader.
- **O3** The server parses the query text (`tl_core.query.parse`). A `QuerySyntaxError` is HTTP 400 `{error, message, position}`. `ClientInterface` gains `query_records(scope, q, *, limit, offset, order_by) -> list[dict]` and `count_records(scope, q) -> int`; WS-D implements them in the embedded and remote clients. MCP `search_records` takes the same `q` text.
- **O4** Each `ServiceError` subclass maps to one status code and a stable machine `error` code, in one table in one module (`tl_api/errors.py`).
- **O5** The API holds no business rules. Routes call `tl_core` services or handlers through a unit of work from a factory (`Backend`); P0-I5's Postgres factory swaps in with the same call shape.
- **O6** SSE tests use httpx streaming against a loopback server with short timeouts; MCP tests call the server in-process.
- **O7** New dependencies are delegated approvals; licences are named in the relay NOTE (see *Dependencies and licences*).

## Demo
```
just demo P0-I4-C
```
Starts the API on a temporary ledger (loopback, a fresh dev token), creates records over HTTP, queries them with the query language
(including a syntax error with its position), streams events with SSE while a second process writes, resumes with `Last-Event-ID`,
uploads and downloads a file (attachment and nosniff headers), and runs the four MCP read tools in-process against the same ledger.
(Script and output: round 3.)

## Published interfaces (for WS-D and later increments)

### Run it
```
uv run tl init                                  # the ledger (TL_DB, default ./dev/data/tl.db)
uv run tl dev token add user:alice              # prints a token; stored in ./dev/data/tokens.json (TL_TOKENS)
just serve                                      # 127.0.0.1:8765; --insecure-dev for another bind
curl -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:8765/records?scope=project:P123&q=status:open'
```

### Backend seam (O5)
```python
# tl_api.backend
class Backend(Protocol):
    ledger: Ledger (property); bus: Bus (property)
    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...
    def close(self) -> None: ...
def open_sqlite_backend(path) -> Backend           # tl_adapters.sqlite.factory.SqliteUowFactory: one engine, one InProcessBus
# tl_api.app
def create_app(backend, *, settings: ApiSettings | None = None, tokens: TokenStore | None = None,
               files_service: FileService | None = None, authorize_hook: Authorizer = authorize) -> FastAPI
```
`factory(readonly)` is the same call shape as `tl_tui.embedded.UowFactory`. P0-I5 adds `PostgresUowFactory` with that shape and a `ledger`/`bus`/`close()`.

### Routes (the committed document is `docs/reference/openapi.json`; `just check` fails when it drifts)
| Method and path | Purpose | Ticket |
|---|---|---|
| `GET /health` | liveness, no token | S |
| `GET /records` | `scope`, `q`, `record_type`, `status`, `include_voided`, `limit` (1–5000, 500), `offset`, `order_by` (`col[:asc\|:desc],...`) | T40 |
| `GET /records/count`, `/records/lookup?scope&key`, `/records/{id}`, `/records/{id}/history` | count, by key, one (ETag = version), events | T40 |
| `GET /records/{id}/links`, `/trace`, `/expected-links`; `GET /links/counts`, `/links/search` | links, n-hop tree, missing expectations, counts, picker | T41 |
| `GET /relations`, `/relations/default`, `POST /keys/detect`, `GET /records/{id}/workflow`, `/schema/forms`, `/records/{id}/conformance` | vocabulary, key chips, workflow status, form metadata, conformance | T42 |
| `POST /commands/{CommandName}` | `CreateRecord`, `UpdateRecord`, `EditRecord`, `SetPsetValues`, `AddLink`, `SuggestLink`, `AcceptLink`, `DeclineLink`, `RepinLink`, `VerifyLink`, `FlagLink`, `RetractLink`, `TransitionWorkflow` | S |
| `GET /events?after&scope&type&record_id&limit` | paged pull: `{events, next_seq, has_more}` | S |
| `GET /stream` | SSE push (below) | S |
| `POST /uploads`, `PUT /uploads/{id}/content?scope`, `POST /uploads/{id}/complete?scope`, `POST /files/attach`, `GET /records/{id}/files`, `GET /files/{id}`, `GET /files/{id}/content` | upload flow and downloads | S |

A command body is the shared command model **without `actor`** (the token's actor is used; a body that carries `actor` is 422) and with
optional `source` (default `api`, pattern `^[a-z][a-z0-9_]*(:[A-Za-z0-9_.-]+)?$`). The response is the model's `CommandResult`. `TransitionWorkflow.actor_roles`
is taken on trust, as the service documents; roles are a human gate.

### Errors (O4)
Body: `{"error": <code>, "message": <text>, "position"?: int, "issues"?: [...], "results"?: [...]}`. One row per class in `tl_api/errors.py`
(`ERROR_TABLE`, 43 rows; `test_error_table.py` fails when a `ServiceError` subclass has none). 400 `query_syntax`, `upload_*`; 401 `unauthorized`;
403 `forbidden`, `file_quarantined`; 404 `*_not_found`; 409 `concurrency_conflict`, `guard_failed`, `duplicate_*`, `record_voided`, `invalid_*`;
413, 415; 410 `file_rejected`; 422 `validation_error` and the rest of the service validation errors; 503 `unavailable`, `object_missing`.
`exception_for(status, body)` rebuilds the exception class from a body, so a remote caller catches `RecordNotFoundError`, `ConcurrencyError`,
`GuardFailedError` (with `results`) and `QuerySyntaxError` (with `position`) exactly as an embedded one does. Bodies the table has no class
for become `ApiError(status, error, message, body)`; a 422 `validation_error` becomes `ApiValidationError` (not a pydantic `ValidationError`:
WS-D adds `ApiError` to `CLIENT_ERRORS`).

### SSE contract
`GET /stream?after=&scope=&type=&record_id=` with `Authorization: Bearer ...`. Each message: `id: <seq>`, `event: <event type>`, `data: <Event JSON>`.
`Last-Event-ID: <seq>` (or `after`) replays the ledger after that seq in pages and then goes live with no gap and no repeat; without either the
stream is live only. `: connected` is sent first and `: keep-alive` when idle (15 s). Events written in this process arrive through the bus;
events written by another process (an embedded TUI on the same SQLite file) arrive through a poller (default every 0.25 s, so well inside the
2 s demo target). At most 32 streams are open (`503 unavailable` beyond that); a consumer that lags 1000 events is resubscribed from its last seq.

### Dev identity (ADR-0005)
`Authorization: Bearer <token>`; `dev/data/tokens.json` maps token to actor (`user:<id>` or `agent:<id>`), mode 0600, re-read when it changes.
A file readable by group or others is refused: nobody authenticates, `add_token` raises and `python -m tl_api` will not start (`chmod 600`).
`add_token` holds an `flock` on `<file>.lock` and renames a unique scratch file into place, so concurrent callers keep every token.
An ASGI middleware (`AuthenticationMiddleware`) resolves the token before anything reads the request: no or unknown token is 401 for every path
except `/health`, including unknown paths, `/openapi.json` and bodies that are not JSON. Every route also depends on `guard(action)`, which calls
`authorize(actor, action, request path)` once; `test_every_route_calls_the_hook` proves it with a deny-all hook, `/openapi.json` included (it is
served by the app behind a token and left out of its own document; `docs/reference/openapi.json` is the public description).
`python -m tl_api` refuses a non-loopback `--host` unless `--insecure-dev`, which logs a warning on every request.

### Dependencies and licences (O7; ADR-0006 scan of the full closure)
Declared: `tl-api` fastapi, uvicorn, httpx2, pydantic, tl-core, tl-schema, tl-adapters; `tl-mcp` mcp, pydantic, tl-core, tl-schema, tl-adapters; `tl-cli`
gains `tl-api` (workspace). The closure holds MIT (fastapi, mcp, mcp-types, pydantic, anyio, annotated-doc, pyjwt, truststore, h11 ...), BSD-3-Clause (uvicorn,
starlette, httpx2, httpcore2, sse-starlette, click, idna), Apache-2.0 (opentelemetry-api, python-multipart) and PSF-2.0 (typing-extensions) distributions. No GPL, LGPL, AGPL or MPL.
`sse-starlette` is not declared: the stream is hand-rolled (`tl_api/feed.py`).

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | `tl_api.errors` table, `tokens.py`, `auth.py` (hook, `guard`, `AuthenticationMiddleware`), `settings.py`, `backend.py`, `tl_adapters.sqlite.factory.SqliteUowFactory` | Auth, identity and the error contract (`01-tiers.md` §3: auth is Sonnet-tier with a human gate; this is the dev stub of ADR-0005) | Orchestrator | built; 77 tests |
| S2 | `app.py` (factory, handlers, lifespan, insecure-dev warning), `openapi.py` and the `just check` drift gate, `main.py` and `just serve` | Wires every route to auth and the error table | Orchestrator | built |
| S3 | `feed.py` (hub, SSE framing, catch-up then live, overflow resume, stream cap), `routes/events.py` | Delivery ordering and concurrency (L-P0-I1-9, L-P0-I4-A2) | Orchestrator | built; 14 tests incl. resume, poller, backlog paging |
| S4 | `commands.py` (command table and generated routes), `routes/files.py` (upload flow, download headers, quarantine rule) | Security surface (O2) and the contract with the services | Orchestrator | built; 34 tests |
| S5 | `tl_api.client.base` (transport, auth header, error mapping, command helper), the `ApiClient` assembly | Error contract on the client side | Orchestrator | built; method groups are T46–T48 |
| S6 | `tl_mcp` server: `build_server(factory, actor=...)`, tool schemas, authorise hook, error mapping, `python -m tl_mcp`, test harness | Identity on MCP (actor from the command line) and the error contract | Orchestrator | built; 7 tests |
| S7 | Demo `dev/demos/P0-I4-C.sh`, READMEs, AGENTS, report | Closing work | — | round 3 |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I4-T40 | Record read routes (14 provided tests) | H | S2 | merged | pass, 1 round (implementer passed `core.hooksPath=/dev/null` to one commit; no hooks are installed, so nothing was skipped) |
| P0-I4-T41 | Link read routes (9 provided tests) | H | S2 | merged | pass, 1 round |
| P0-I4-T42 | Reference read routes (9 provided tests) | H | S2 | merged | pass, 1 round |
| P0-I4-T45 | `tl dev token add` (6 provided tests) | H | S1 | merged | pass, 1 round |
| P0-I4-T43 | MCP read tool and resource bodies (14 provided tests) | H | S6 | ready (batch 2) | |
| P0-I4-T46 | HTTP client: records, queries and commands (11 provided tests) | H | S5, T40 | ready (batch 2) | |
| P0-I4-T47 | HTTP client: links, workflow, schema and reference (10 provided tests) | H | S5, T41, T42 | ready (batch 2) | |
| P0-I4-T48 | HTTP client: files and events, SSE with resume (7 + 8 provided tests) | H | S5 | ready (batch 2) | |

Haiku-ability (`01-tiers.md` §6), batch 1: (1) three or four files to read; (2) the stubs, the harness and every service signature are in the
repository; (3) each ships a provided test (14, 9, 9 and 6 tests) verified against a scratch reference with `ruff`, `pyright` and the OpenAPI
check; (4) diffs of 40 to 90 lines plus the copied test; (5) none is in the Sonnet-authored table (the routes are one-call wrappers, the CLI command
calls one function; identity and the error table are supervisor-built); (6) no schema, migration, dependency or public-interface change (the
dependency edits and the OpenAPI document are committed on the base); (7) a reviewer verifies from the diff and the commands.

## Order of work
1. Round 1 (done): dependencies and licence scan, S1–S4, stubs and provided tests, tickets T40, T41, T42, T45. Dispatched and merged (review pass).
2. Round 2 (this relay): S5 and S6; stubs, provided tests and tickets for T43, T46, T47, T48; dispatch.
3. Round 3: merge batch 2; ApiClient assembly and a round-trip test through the whole `ClientInterface`; demo, READMEs, AGENTS, runbook, report; publish the final client signatures here; DONE.

## Design decisions taken by the supervisor (within the plan's scope)
| # | Decision | Why |
|---|---|---|
| C1 | `POST /commands/{CommandName}` (brief 11.1) with one generated route per command and a request model derived from the shared model (no `actor`, optional `source`, unknown fields refused). The real command model is then built from it, so its validators run | Precise OpenAPI per command, one source of truth for rules, and `actor` cannot be forged |
| C2 | `GET /records` always runs through `run_query`; `status` is ANDed into the parsed AST | One query path; `list_records`'s `status` filter and `q` cannot disagree |
| C3 | `/records/lookup?scope&key` and `/records/count` instead of `by-key/{key}` | A key such as `links` cannot collide with a sub-resource; count is a cheap second call |
| C4 | The backend is `SqliteUowFactory` in `tl_adapters.sqlite.factory` (new module in an existing package), not in `tl_api` | The factory is adapter composition shared by the API and MCP, and the Postgres factory will sit beside it. No file of P0-I5 is touched. **Orchestrator ruling C4:** P0-I5 WS-B has a file at the same path; P0-I4 reaches the trunk first, so this one is canonical. `readonly` is positional-or-keyword, `close()` has the alias `dispose()`, and `engine`, `ledger` and `bus` (default `InProcessBus`) stay public, so P0-I5 adopts it unchanged |
| C5 | Unit-of-work scope: one per request, opened inside the handler (never a `yield` dependency) | The response must not be built before the commit (L-P0-I4-C1) |
| C6 | `PUT /uploads/{id}/content` spools the body to a temporary file (8 MiB in memory) up to `max_upload_bytes` (5 GiB), then the service verifies size and hash | The service needs a blocking `BinaryIO`; the cap bounds disk use. A cap taken from the declared size would be tighter (follow-up) |
| C7 | Downloads proxy bytes with `application/octet-stream`, `attachment`, `nosniff`, a restrictive CSP and `no-store`; presigned download URLs are not exposed | O2; the fs backend's `file://` URLs mean nothing over HTTP and S3 URLs would bypass the headers |
| C8 | At most 32 concurrent SSE streams, each on a dedicated worker thread | A blocked queue read must not starve the request thread pool; refusing beyond the cap is explicit |
| C9 | The change-feed poller starts in the app lifespan and builds its cursor then | Creating an app (for OpenAPI generation) touches no storage |
| C10 | `TransitionWorkflow.actor_roles` stays in the request body | The core documents it as a trusted stub until auth exists; removing it would break `ClientInterface.transition` |
| C11 | `void_record`, `MarkPinsStale` and file commands are not in the command table | Not in the Phase 0 client contract; files have upload routes |

## Risks and escalation triggers
- The OpenAPI document is committed output of the route table: any signature change in a ticket turns `just check` red. Stubs keep it final; a reviewer should run `just check`.
- SSE under Postgres inherits L-P0-I4-A2 (out-of-order commit visibility); the Postgres factory must give the poller a lagging cursor. Nothing here changes it.
- The dev token file is plaintext by design (ADR-0005); nothing in Phase 0 is deployable.
- Escalate for: any change to `QuerySpec`/AST or the command models (contracts), a decision on roles (human gate), a need for `iter_keys` through the `ObjectStore` Protocol.

## Blocked / Decision
(none)
