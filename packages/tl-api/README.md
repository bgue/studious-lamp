# tl-api (`tl_api`)

The REST API, the SSE change stream and the HTTP client over the `tl_core` services (§11.1, §18.1 to §18.3, §20). Identity is real since P1-I0 (ADR-0009): accounts, sessions, agent tokens, two roles; the dev token file of ADR-0005 survives only for `TL_ENV` dev, test and ci.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_api.app.create_app(backend, *, settings, tokens, files_service, authorize_hook)` | function | Build the FastAPI app over a `Backend`. No state beyond `app.state.ctx` |
| `tl_api.backend.Backend`, `open_backend(target)` | protocol, function | The storage seam: `backend(readonly)` yields an entered unit of work; `.ledger`, `.bus`, `.close()`. `open_backend` takes a SQLite path or a `postgresql://` URL (`tl_adapters.backend`); the live feed gets the bus for this process's writes and a 0.25 s poll for other processes' |
| `tl_api.errors` (`ERROR_TABLE`, `body_for`, `exception_for`, `ApiError`) | module | The one table that maps each `ServiceError` to a status and a stable `error` code, both directions |
| `tl_api.auth` (`guard`, `Resolver`, `current_principal`, `AuthenticationMiddleware`, `BodyLimitMiddleware`) | module | A bearer token (session, agent or dev) becomes a `Principal` before any request body is read; `guard(action)` runs the role `Authorizer` (closed for agents, `admin.*` for admins, `control.*` for admins and the listed document controller actions) and returns the actor. `authorize` is the old allow-all hook the MCP server and tests may still pass |
| `tl_api.ratelimit` (`SourceLimiter`, `RateLimitMiddleware`, `client_key`) | module | 20 failed `POST /auth/sign-in` per client address in 10 minutes, then 429 `rate_limited` with `Retry-After` before any hash. In memory, per process: a second layer behind a front-door limiter |
| `tl_api.routes.auth`, `tl_api.client.auth` (`sign_in`, `AuthApi`) | routes, client | `POST /auth/sign-in` (open), `/auth/sign-out`, `GET /auth/me`, `POST /auth/password` and the client calls; failures raise the embedded exception classes |
| `tl_api.routes.admin`, `tl_api.client.admin.AdminApi` | routes, client | `/admin/accounts` (list, create, get, roles, disable, enable, password) and `/admin/tokens` (list, issue, revoke), all `admin.*` actions: only a human admin (403 `forbidden` for users, document controllers, agents and dev tokens); roles are `admin`, `document_controller`, `user`. `PUT .../roles` takes an optional `expected_roles`: the list the caller read; a mismatch is 409 `account_state` and nothing is written. A token is returned once, with a hidden `repr` |
| `tl_api.tokens` (`TokenStore`, `add_token`, `check_actor`) | module | The dev token file: `{token: actor}`, mode 0600, re-read on change |
| `tl_api.commands.COMMANDS` | table | The 17 commands served as `POST /commands/{Name}`, one generated route each (13 record, link and workflow commands, then `PostToFeed`, `EditPost`, `RetractPost`, `ReactToPost`). A request may carry `X-TL-Effective-At` (ISO-8601 with offset, years 1970 to 2100): honoured only when the command's scope is `project:sim-<run>`, where it becomes the events' `effective_at`; any other scope is 400 `effective_time_forbidden`, a bad value 400 `invalid_effective_time` (`tl_api.effective`). `POST /proposals/{id}/accept` and `/reject` take the same header, checked against the proposal's scope, so a simulated decision and the command it runs carry simulated time |
| `tl_api.feed.FeedHub` | class | Subscription registry fed by the bus and a poller; SSE framing; stream cap |
| `tl_api.client.ApiClient(base_url, token, *, http=None, timeout=30)` | class | The HTTP client WS-D wraps as the remote `ClientInterface` (signatures: `docs/tickets/P0-I4/README-C.md`) |
| `tl_api.routes.settings` | routes | about:config over HTTP: `GET /settings`, `/settings/{key}`, `/settings/{key}/history`, `/settings/diff`, `/settings/export`; `PUT /settings/{key}`; `POST /settings/{key}/reset|lock|revert` and `/settings/import`; plus `POST /commands/ChangeSetting` and `accept_risk` in the proposal accept body. Every write is refused for an `agent:` token (403 `agent_must_propose`); errors are the `SettingError` rows of `tl_api.errors` (404 `unknown_setting`, 409 `setting_locked` and `setting_revert_not_latest`, 422 for the rest) |
| `tl_api.client.settings.SettingsApi` | mixin of `ApiClient` | `list_settings`, `get_setting`, `setting_history`, `set_setting`, `reset_setting`, `lock_setting`, `revert_setting`, `diff_settings`, `export_settings`, `import_settings`; the first seven are `ClientInterface` methods of the TUI |
| `tl_api.main.mark_server_started` | function | Records that settings with `effect: restart` are now in force (`setting_effect_applied`); `python -m tl_api` calls it before serving |
| `tl_api.client.feed.FeedApi`, `tl_api.client.proposals.ProposalsApi` | mixins of `ApiClient` | `feed_page`, `feed_post`, `feed_edit`, `feed_retract`, `feed_react`, `feed_complete` (same signatures as `ClientInterface`); `list_proposals`, `get_proposal(id, scope)`, `accept_proposal`, `reject_proposal` (extras, not on `ClientInterface`) |
| `tl_mod_engineering.commands.API_COMMANDS`, `tl_api.commands.CommandSpec.access` | commands | The engineering module's 14 commands as `POST /commands/<Name>`; `access` is `admin` (action `admin.command.<Name>`, 403 `forbidden` for users and agents), `controller` (action `control.command.<Name>`: an admin, or a document controller for the exact actions of `tl_api.commands.controller_actions()`; ADR-0013), `company` (admin only when `scope` is `company`) or `user`. Agents get `agent_must_propose`. The generic record commands refuse module records the module does not list (422 `unsupported_record_type`, ADR-0010 addendum) |
| `tl_api.routes.engineering`, `tl_api.client.engineering.EngineeringApi` | routes, client | Reads: `GET /standards`, `/standards/{kind}/{code}`, `/code-lists/{name}/values`, `/tag-classes[/{code}]`, `/projects/{project}/tags[/{number}]` (actions `standards.read`, `tag.read`, open to agents); the client has `list_tags`, `get_tag`, `create_tag`, `rename_tag` |
| `tl_api.routes.documents`, `tl_api.client.documents.DocumentsApi` | routes, client | Reads (action `document.read`, open to agents): `GET /projects/{project}/documents`, `/documents/{number}`, `/document-diffs/{number}?from=&to=`, `/stale-links`, `/overdue-reviews`, `/transmittals[/{number}]`; a number may hold `/` (`{number:path}`). The 24 document commands are `POST /commands/<Name>` with their access (`user` or `controller`, ADR-0013: the ten controlling acts are a document controller's or an admin's). The client has the reads and `register_document`, `create_revision`, `repin_document_link`, `create_transmittal`, `issue_transmittal` |
| `tl_api.auth.BodyLimitMiddleware`, `ApiSettings.max_command_bytes` (`TL_API_MAX_COMMAND_BYTES`) | middleware, setting | A `/commands/` body over 1 MiB (default) is a 413 `payload_too_large` before it is parsed |
| `tl_api.routes.extypes` | module | Extension record types (brief 31): `GET /types?status=`, `GET /types/{type_ref}` (with its generated form), `POST /types/{type_name}/records` (`psets` for a managed type, `body` for an object-backed one), `GET /records/{id}/body` (hash-verified; 502 `body_hash_mismatch`, 403 `body_quarantined`), `PUT /records/{id}/body` (`expected_version`; 422 `body_invalid` lists the problems). The two writes refuse an `agent:` token. `create_app(object_store=)` is the store that holds bodies (503 `body_store_unavailable` without one) |
| `tl_api.client.types_api.TypesApi` | mixin of `ApiClient` | `list_types`, `get_type`, `create_instance`, `get_record_body`, `put_record_body`: the same models and exception classes as the embedded services |
| `tl_api.openapi` | module | `python -m tl_api.openapi [--check]`; the document is `docs/reference/openapi.json` |
| `python -m tl_api` / `just serve` | command | Run the server (loopback only unless `--insecure-dev`) |
| `tl_api.context.ApiContext` | class | The per-application context route handlers read from `request.app.state` |
| `tl_api.main` | module | The server entry point: `uv run python -m tl_api` (or `just serve`) |
| `tl_api.models` | module | Response and request models that have no `tl_core` class of their own |
| `tl_api.routes.derivation`, `tl_api.client.derivation.DerivationApi` | routes, client | Derivation reads (action `document.read`, open to agents): `GET /projects/{project}/document-schemas[/{ref}]`, `/derived-documents[/{ref}]`, `/processing-jobs[/{id}]`, `/derived-rows/{ref}`, `/derived-reports/{ref}`, `/derived-diffs/{ref}`, `/derived-publish-previews/{ref}`, `/derived-compensation-previews/{ref}`; `{ref}` is an id or a key (`ISD-001@A/instrument-index`). No route applies a JSON Schema to rows: a report is the one a job stored. Commands are `POST /commands/<Name>` (`RegisterDocumentSchema`, `PublishDerivedTags` and `CompensatePublication` admin; `PublishDerivedDocuments` and `VoidDerivedDocument` controller; the rest user). A command that carries a `derive:` correlation id or an `import:derived-*` or `compensation:*` source is refused (422 `reserved_identifier`) |

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
| `TL_DB` / `--db` | `./dev/data/tl.db` | The ledger: a SQLite file or a `postgresql://` URL (prefer the variable for a URL, it carries the password); create it with `tl init`. `ApiSettings.db_path` holds it as a `DbTarget` |
| `TL_TOKENS` / `--tokens` | `./dev/data/tokens.json` | Must be mode 0600; a looser file is refused and the server will not start |
| `TL_API_HOST`, `TL_API_PORT` / `--host`, `--port` | `127.0.0.1`, `8765` | A non-loopback host needs `--insecure-dev`, which logs a warning per request |
| `TL_OBJECT_STORE`, `TL_OBJECT_ROOT`, `TL_OBJECT_SECRET`, `TL_ENV=dev` | `fs`, `./dev/data/objects` | As the CLI; without a store the file routes answer 503 |
| `TL_ENV` | unset (`just` exports `dev`) | `dev`, `test`, `ci` honour the dev token file; `demo` and `test` may hold the `demo` account; the server refuses to start on a non-loopback address, or in any other environment, while `demo` is enabled |
| `TL_TRUSTED_PROXY_HEADER` | unset | Header a trusted reverse proxy sets with the client address (`X-Forwarded-For`); the last line's last entry counts, so the proxy must overwrite or append. Unset: the socket peer. IPv6 clients count by /64 |

## Behaviour to know
- Errors are `{"error": <code>, "message": ..., "position"?, "issues"?, "results"?}`. 404 not found, 409 version or state conflict or failed guard, 422 validation, 400 for query syntax and upload tokens. The client raises the same exception classes an embedded call raises; a server it cannot reach raises `ApiUnavailableError`.
- A command body is the shared command model without `actor` (the token's actor is used; sending one is a 422); `source` defaults to `api`.
- SSE: `id: <seq>`, `event: <type>`, `data: <Event>`; resume with `Last-Event-ID`; at most 32 streams.
- Feed: only a post's author may edit or retract it (403 `not_post_author`); reactions are open. On every feed command an `agent:` token sends, the server sets `source` to `mcp:<agent id>`.
- Review queue: agents propose through MCP, a person decides here. Accept runs the stored command as the token's actor with `source=mcp:<agent>`; a command that can no longer be applied is a 200 whose proposal has `status: failed` and the error in `reason`. An `agent:` token is refused with 403 `proposal_decider`. An `agent:<id>` token cannot change a record over REST (B15): every command except `PostToFeed`, `EditPost`, `RetractPost`, `ReactToPost`, and the file writes, answer 403 `agent_must_propose`; agents read, post, and propose through MCP. People may do everything except `admin.*` (admins only); an agent only what `AGENT_ACTIONS` lists. Budget refusals are 429 `budget_exceeded`.
- Downloads are `application/octet-stream` with `Content-Disposition: attachment` and `nosniff`; a quarantined file goes to its uploader only.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
P1-I1: the engineering routes, commands, error rows (21), request limit and client calls (`docs/tickets/P1-I1/README.md`; security review fixes in ADR-0010's addendum). Introduced in P0-I4 (workstream C). Last interface change: P0-I8 workstream A (the `/settings` routes, `SettingsApi`, `ChangeSetting` as a command; `docs/tickets/P0-I8/README-A.md`), earlier: P0-I6 workstream B (feed and review-queue routes, five proposal rows in the error table). P1-I0 workstream A replaced the identity stub with ADR-0009 (`docs/tickets/P1-I0/README-A.md`): `/auth/*`, `/admin/*`, the principal in `guard`, the rate limiter, 413 `payload_too_large`, 503 `auth_busy`. Operations: `docs/runbooks/accounts-and-access.md`. Extension type routes and client methods added in P0-I8 workstream B (nine error rows; `docs/tickets/P0-I8/README-B.md`).
