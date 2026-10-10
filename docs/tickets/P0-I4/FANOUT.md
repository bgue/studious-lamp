# Fanout plan — P0-I4 Files/uploads, REST API, MCP read tools, change feed, live TUI

Status: active
Orchestrator session: 2026-10-09
Brief sections: §5.3, §7.5, §10.2, §11, §18.1–§18.3, §19.1, §20, §4 (embedded vs remote client)

## Objective
Records are queryable through one query language from the TUI, the REST API and MCP; files attach to records through
a content-addressed object store; changes stream to subscribers; a remote TUI and an MCP agent see the same record
change within 2 s of an embedded TUI writing it.

## Exit criteria
- [ ] `parse` + `run_query` cover the AST in `tl_core/query/ast.py` (except `path(...)`), with SQL from allow-lists and bound params only.
- [ ] Files: `fs` object store (default) and `s3` (moto-tested); upload with hash verify and dedupe; `File.*` events; `cur_files`; quarantine flag; `tl file put/get`.
- [ ] REST: `/records`, `/records/{id}`, `/records/{id}/links`, `/events?after=`, commands endpoint, SSE stream; OpenAPI check; local-accounts auth stub (see Human gates).
- [ ] MCP server: read tools `search_records`, `get_record`, `get_links`, `trace`; resources.
- [ ] Remote `ClientInterface` over HTTP + SSE; live row highlight; conflict banner via `stream_version`; filter bar wired to the query language.
- [ ] Demo: embedded TUI writes, remote TUI and an MCP client observe the change in < 2 s.

## Workstreams

| WS | Name | Branch / worktree | Base | Provides | Consumes |
|---|---|---|---|---|---|
| A | Query language + change feed | `p0/i4a` · `/home/user/wt/p0-i4a` | `p0/i4` (now) | `parse`, `run_query`, `count_query`; seq-cursor poller and subscription registry | contracts below |
| B | Files | `p0/i4b` · `/home/user/wt/p0-i4b` | `p0/i4` (now) | `ObjectStore` backends, upload service, `File.*`, `cur_files`, file slots in LinkML, CLI | `files/types.py` |
| C | API + MCP | `p0/i4c` | `p0/i4` after P0-I3 and A merge | FastAPI app, routes, SSE, MCP server | A, B, P0-I3 links/workflow services |
| D | Live TUI | `p0/i4d` | after C | remote ClientInterface, live updates, filter bar | A, C |

A and B start now from `p0/i4` (cut from `p0/i3` at e881656, which has links, numbering and workflow schema and
engines). When P0-I3 merges into the trunk, the orchestrator merges the trunk into `p0/i4`, and A and B merge `p0/i4`.

## Shared contracts (committed on `p0/i4`)
- `packages/tl-core/src/tl_core/query/ast.py`: AST nodes and surface syntax table.
- `packages/tl-core/src/tl_core/query/api.py`: `QuerySpec`, `QuerySyntaxError`, `parse`, `run_query`, `count_query`, and the compile rules (allow-listed columns, pset paths via `cur_pset_values` EXISTS, links via `cur_links`).
- `packages/tl-core/src/tl_core/files/types.py`: `ObjectStore` Protocol (03 §7), `object_key`, `ObjectNotFound`.
WS-B publishes its upload-service signatures in README-B before WS-C starts; WS-A publishes the poller and subscription signatures in README-A.

## Merge order and conflict owner
A → B → (trunk sync) → C → D, merge commits only. Conflicts are resolved by the later-merging workstream's supervisor.
D writes `dev/demos/P0-I4.sh` and `docs/reports/P0-I4.md`.

## Human gates
| Gate | Approver | Where recorded |
|---|---|---|
| File slot LinkML, `File.*` events, `cur_files` schema | Orchestrator under KICKOFF delegation (§20) | APPROVALS.md |
| API auth stub | Orchestrator decision, recorded as ADR-0005 before WS-C starts: dev-only local identity, no authorization model; a real auth model stays a human gate | ADR + APPROVALS.md |

## Risks
- SSE and WebSocket testing without a browser: use httpx streaming in tests; keep timeouts short.
- Query compile on Postgres is not exercised until P0-I5; keep it dialect-neutral (no json_extract; use `cur_pset_values`).
