# tl-api (`tl_api`)

The REST API, the SSE change stream and the HTTP client over the `tl_core` services (§11.1, §18.1 to §18.3, §20). Phase 0 identity is the dev-only stub of ADR-0005.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_api.app.create_app(backend, *, settings, tokens, files_service, authorize_hook)` | function | Build the FastAPI app over a `Backend`. No state beyond `app.state.ctx` |
| `tl_api.backend.Backend`, `open_sqlite_backend(path)` | protocol, function | The storage seam: `backend(readonly)` yields an entered unit of work; `.ledger`, `.bus`, `.close()`. SQLite today (`SqliteUowFactory`), Postgres in P0-I5 |
| `tl_api.errors` (`ERROR_TABLE`, `body_for`, `exception_for`, `ApiError`) | module | The one table that maps each `ServiceError` to a status and a stable `error` code, both directions |
| `tl_api.auth` (`authorize`, `guard`, `AuthenticationMiddleware`) | module | Token lookup before any request is read; the allow-all hook every route calls |
| `tl_api.tokens` (`TokenStore`, `add_token`, `check_actor`) | module | The dev token file: `{token: actor}`, mode 0600, re-read on change |
| `tl_api.commands.COMMANDS` | table | The 17 commands served as `POST /commands/{Name}`, one generated route each (13 record, link and workflow commands, then `PostToFeed`, `EditPost`, `RetractPost`, `ReactToPost`). A request may carry `X-TL-Effective-At` (ISO-8601 with offset, years 1970 to 2100): honoured only when the command's scope is `project:sim-<run>`, where it becomes the events' `effective_at`; any other scope is 400 `effective_time_forbidden`, a bad value 400 `invalid_effective_time` (`tl_api.effective`) |
| `tl_api.feed.FeedHub` | class | Subscription registry fed by the bus and a poller; SSE framing; stream cap |
| `tl_api.client.ApiClient(base_url, token, *, http=None, timeout=30)` | class | The HTTP client WS-D wraps as the remote `ClientInterface` (signatures: `docs/tickets/P0-I4/README-C.md`) |
| `tl_api.client.feed.FeedApi`, `tl_api.client.proposals.ProposalsApi` | mixins of `ApiClient` | `feed_page`, `feed_post`, `feed_edit`, `feed_retract`, `feed_react`, `feed_complete` (same signatures as `ClientInterface`); `list_proposals`, `get_proposal(id, scope)`, `accept_proposal`, `reject_proposal` (extras, not on `ClientInterface`) |
| `tl_api.openapi` | module | `python -m tl_api.openapi [--check]`; the document is `docs/reference/openapi.json` |
| `python -m tl_api` / `just serve` | command | Run the server (loopback only unless `--insecure-dev`) |

Routes: `GET /health` (no token); `/records` (query language, paging, ordering), `/records/count`, `/records/lookup`, `/records/{id}`, `/history`, `/links`, `/trace`, `/expected-links`, `/workflow`, `/conformance`, `/files`; `/links/counts`, `/links/search`; `/relations`, `/relations/default`, `/keys/detect`, `/schema/forms`; `POST /commands/{Name}`; `/events?after=` (paged) and `/stream` (SSE, `Last-Event-ID`); `/uploads`, `/files/attach`, `/files/{id}`, `/files/{id}/content`; the feed: `GET /feed`, `/feed/complete`, `/feed/posts/{id}` (writes are `POST /commands/PostToFeed|EditPost|RetractPost|ReactToPost`); the review queue: `GET /proposals`, `GET /proposals/{id}?scope=` (scope required), `POST /proposals/{id}/accept`, `POST /proposals/{id}/reject`; `/openapi.json` (token required). The full list with parameters is the committed OpenAPI document.

## Depends on / used by
- Depends on: `tl_core`, `tl_schema`, `tl_adapters`, `fastapi`, `uvicorn`, `httpx2`, `pydantic`.
- Used by: `tl_cli` (token helper), `tl_mcp` (hook, actor check, query parameters), the remote TUI client (WS-D), `just serve`, `just demo P0-I4-C`.

## Commands
```
just serve                                   # 127.0.0.1:8765 on TL_DB with TL_TOKENS
uv run tl dev token add user:alice           # prints a token
just test packages/tl-api
uv run python -m tl_api.openapi              # regenerate docs/reference/openapi.json
just demo P0-I4-C
```
Runbook: `docs/runbooks/api-and-mcp-dev.md`.

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_DB` / `--db` | `./dev/data/tl.db` | SQLite ledger; create it with `tl init` |
| `TL_TOKENS` / `--tokens` | `./dev/data/tokens.json` | Must be mode 0600; a looser file is refused and the server will not start |
| `TL_API_HOST`, `TL_API_PORT` / `--host`, `--port` | `127.0.0.1`, `8765` | A non-loopback host needs `--insecure-dev`, which logs a warning per request |
| `TL_OBJECT_STORE`, `TL_OBJECT_ROOT`, `TL_OBJECT_SECRET`, `TL_ENV=dev` | `fs`, `./dev/data/objects` | As the CLI; without a store the file routes answer 503 |

## Behaviour to know
- Errors are `{"error": <code>, "message": ..., "position"?, "issues"?, "results"?}`. 404 not found, 409 version or state conflict or failed guard, 422 validation, 400 for query syntax and upload tokens. The client raises the same exception classes an embedded call raises; a server it cannot reach raises `ApiUnavailableError`.
- A command body is the shared command model without `actor` (the token's actor is used; sending one is a 422); `source` defaults to `api`.
- SSE: `id: <seq>`, `event: <type>`, `data: <Event>`; resume with `Last-Event-ID`; at most 32 streams.
- Feed: only a post's author may edit or retract it (403 `not_post_author`); reactions are open. On every feed command an `agent:` token sends, the server sets `source` to `mcp:<agent id>`.
- Review queue: agents propose through MCP, a person decides here. Accept runs the stored command as the token's actor with `source=mcp:<agent>`; a command that can no longer be applied is a 200 whose proposal has `status: failed` and the error in `reason`. An `agent:` token is refused with 403 `proposal_decider`. An `agent:<id>` token cannot change a record over REST (B15): every command except `PostToFeed`, `EditPost`, `RetractPost`, `ReactToPost`, and the file writes, answer 403 `agent_must_propose`; agents read, post, and propose through MCP. `authorize` still allows everything for people (ADR-0005). Budget refusals are 429 `budget_exceeded`.
- Downloads are `application/octet-stream` with `Content-Disposition: attachment` and `nosniff`; a quarantined file goes to its uploader only.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I4 (workstream C). Last interface change: P0-I6 workstream B (feed and review-queue routes, five proposal rows in the error table). The identity stub is replaced only by an owner-approved auth ADR.
