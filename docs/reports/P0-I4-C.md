# Report — P0-I4 workstream C (REST API, SSE stream, MCP read server, HTTP client)

Branch `p0/i4c` (integration branch `p0/i4`; trunk `claude/wizardly-allen-m2v96s` was not merged in this round, by instruction). Plan and published contracts: `docs/tickets/P0-I4/README-C.md`.

## Outcome
Objective met: yes. `tl_api` serves records (query language, paging, ordering), links, trace, workflow, schema and files, a command endpoint generated from the shared command models, a paged event pull and an SSE stream with `Last-Event-ID` resume, behind the dev-only identity of ADR-0005, with a committed OpenAPI document whose drift fails `just check`. `tl_mcp` serves `search_records`, `get_record`, `get_links`, `trace` and three resources, read-only. `tl_api.client.ApiClient` serves every `ClientInterface` method plus `query_records` and `count_records`; a round-trip test compares it with the embedded client on one ledger. Demo: `just demo P0-I4-C` ran clean on the final tree (the CLI's write was visible on the stream within about a second); the combined P0-I4 demo is workstream D's. Not verified on a fresh clone.

FANOUT criteria owned by C are met: REST (`/records`, `/records/{id}`, links, `/events?after=`, commands, SSE, OpenAPI check, identity stub), the MCP read server with resources, and the client signatures (published in README-C).

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| P0-I4-T40 record routes | merged | 1 | The implementer passed `core.hooksPath=/dev/null` to one commit; no hooks are installed, so nothing was skipped |
| P0-I4-T41 link routes | merged | 1 | |
| P0-I4-T42 reference routes | merged | 1 | Re-reviewed after a usage-limit interruption |
| P0-I4-T45 `tl dev token add` | merged | 1 | Re-reviewed after a usage-limit interruption |
| P0-I4-T43 MCP tool and resource bodies | merged | 1 | Deviation, confirmed: the ticket called `dump` given but the stub had stubbed it; compact key-sorted JSON |
| P0-I4-T46 client records | merged | 1 | |
| P0-I4-T47 client links | merged | 1 | |
| P0-I4-T48 client files and events | merged | 1 | |

No ticket needed a second round; none was taken over; none abandoned. Supervisor pieces (reviewed by fresh security reviewers): error table, dev tokens, authorise hook and middleware, app factory, OpenAPI gate, SSE hub, generated command routes, file routes, the client base, the MCP server skeleton, `SqliteUowFactory`.

## Gates
| Gate | Result |
|---|---|
| `just check` (ruff, format, pyright, codegen drift, OpenAPI drift) | exit 0 |
| `just test` | 2459 passed (23 snapshots) |
| `just test-tui` | 324 passed |
| `just demo P0-I4-C` | OK (stream showed the CLI write about 1 s after the writer process exited; resume from `Last-Event-ID` exact) |
| `test-parity` | not applicable (no Postgres code; the factory seam is ready for P0-I5) |

## Deviations from plan
- `SqliteUowFactory` (`tl_adapters/sqlite/factory.py`) is a new additive file in `tl-adapters`; the fanout named a WS-B factory that did not exist. Orchestrator ruling C4: this file is canonical (`readonly` positional or keyword, `close()` and `dispose()`, public `engine`, `ledger`, `bus`).
- `tl-cli` depends on `tl-api` (token helper) and `tl-mcp` on `tl-api` (hook, actor check, query parameter parsing). Both are workspace dependencies.
- `EventPage` moved from `routes/events.py` to `models.py` so the client can import it without a route module.
- Void, mark-pins-stale and file commands are not in the command table (decision C11).

## Escalations and decisions
- Orchestrator rulings: C4 (canonical factory), and the S1–S4 review (fixes in 4eac270: authentication before the request body, `/openapi.json` behind the token and the hook, token file must be mode 0600 and `add_token` serialised with `flock`, stream slot released by the response).
- Review of S5/S6 at 1b70ecc, fixed in c073261: per-class error handlers (a catch-all `Exception` handler closed keep-alive connections; 20 sequential errors now pass over one pooled connection, at the HTTP level and through `ApiClient`), `ApiUnavailableError` for transport failures (also a `TransportError`, one retry of a reset GET), dot segments refused in paths, MCP input bounds checked before the hook, quoted resource names.
- Orchestrator decisions O1 to O7 are quoted in README-C and were followed. Dependencies and licences were logged by the orchestrator (all MIT, BSD-3-Clause, Apache-2.0 or PSF-2.0).

## Learnings
Appended: L-P0-I4-C1 to C10 (lazy FastAPI routes, real server for SSE tests, endpoints built in loops, mcp 2.x and httpx2, licence scan, stub tickets keep OpenAPI final, authenticate before the body, stub scripts and imports lists, catch-all handlers close connections, given helpers and compatible base-class fixes). Implementer proposals: none declined.

## Docs
`packages/tl-api/README.md` and `AGENTS.md`, `packages/tl-mcp/README.md` and `AGENTS.md`, `packages/tl-cli/README.md` (the `dev token` row), `packages/tl-adapters/README.md` (the factory), `docs/runbooks/api-and-mcp-dev.md` (and its index entry), `docs/tickets/P0-I4/README-C.md` (plan, contracts, final client signatures), `docs/reference/openapi.json` (generated).

## Follow-ups filed
- WS-D: implement `query_records` and `count_records` on `ClientInterface` and the embedded client (O3); add `ApiError` to `CLIENT_ERRORS`; map `RelationOut` to `RelationInfo`; write the P0-I4 demo `dev/demos/P0-I4.sh`.
- MCP resource-change notifications through the change feed (brief 11.3) and MCP over HTTP; propose-only write tools are P0-I6.
- `PUT /uploads/{id}/content` caps the spooled body at 5 GiB regardless of the declared size; a cap taken from the registered size would be tighter (needs the service to expose the claims).
- Presigned download URLs through the API, multipart resume, `void_record` as a command, pagination by cursor (brief 11.1; offset today), ETag on lists.
- P0-I5: the Postgres factory must give the poller a lagging cursor (L-P0-I4-A2); `cur_files` has no unique constraint on (record, slot, revision) (README-B).
- The real authentication and permission model remains a human gate; the dev tokens are plaintext by design (ADR-0005).

## Cost notes
Eight implementer tickets, all passing in one review round. Six fresh reviewer verdicts on supervisor pieces and tickets across the workstream. The account hit its usage limit once during batch 1; two tickets were re-reviewed.
