# Fanout plan — P0-I5 Postgres adapter, parity suite, outbox + webhooks, event catalog

Status: active
Orchestrator session: 2026-10-09
Brief sections: §5.1–§5.4, §14 (Postgres row), §15 (portability), §18.2–§18.4, §19.2; build spec 03 §6, 04 §1

## Objective
Every behaviour that runs on SQLite runs identically on PostgreSQL 16, proven by one parity suite; every committed
event is written to a transactional outbox and delivered as a signed CloudEvents webhook to filtered subscribers,
with retries, a dead-letter queue and replay by seq; a generated event catalog documents every event type.

## Exit criteria
- [ ] `just test-parity` runs the adapter, projector, service, query, change-feed and file tests on SQLite and Postgres (native cluster, `TL_PG_URL`) and both are green.
- [ ] Postgres ledger: append-only enforced by triggers; per-scope hash chain identical to SQLite's for the same events; **commit order equals seq order** (see A3); LISTEN/NOTIFY wake-ups for the poller.
- [ ] Outbox rows written in the same transaction as the events, on both databases.
- [ ] Webhook delivery: Standard Webhooks HMAC headers, per-subject ordering, exponential backoff with jitter, DLQ, replay by seq range, auto-disable after sustained failure; egress allow-list (SSRF); a dev test receiver.
- [ ] Event catalog generated from LinkML: JSON Schema per event type, sample payloads, AsyncAPI document; contract tests check delivered payloads against it.
- [ ] Demo: a filtered subscription receives a signed event; a replay re-delivers a seq range.

## Workstreams

| WS | Name | Branch / worktree | Provides | Consumes |
|---|---|---|---|---|
| A | Postgres adapter + parity | `p0/i5a` · `/home/user/wt/p0-i5a` | `tl_adapters.postgres` (ledger, UoW, engine), DDL application, parity fixtures, `just test-parity`, CI job | core interfaces (03 §7), generated Postgres DDL |
| B | Outbox + webhooks + catalog | `p0/i5b` · `/home/user/wt/p0-i5b` | outbox projector, WebhookSubscription + filter (LinkML), delivery worker, DLQ/replay, event catalog generator, contract tests | change-feed filters from P0-I4 (`tl_core.changefeed.filters`), the projector registry |

Both start from `p0/i5`, which is cut from `p0/i4` (P0-I2 complete, P0-I3 core engines, P0-I4 query language,
change feed and files). P0-I3's final TUI work and P0-I4's API/MCP arrive by trunk merge later.

## Shared contract (no new code; rules both workstreams keep)
- **C1 Outbox is a projector.** WS-B adds `handles_all: bool` support to the projector registry (a registry extension,
  supervisor-built) and implements the outbox as a projector named `outbox` with `handles_all = True`, registered in
  `default_registry`. Any UnitOfWork that runs the registry inline (SQLite today, Postgres from WS-A) therefore writes
  outbox rows in the same transaction with no adapter-specific outbox code.
- **C2 Postgres UoW runs the registry exactly like SQLite's**: same `Projector.apply(conn, event)` calls in seq order,
  inside the write transaction, then ordered bus publish after commit.
- **C3 DDL comes from the generator** (`tl_schema.generators.ddl` postgres dialect). No hand-written `cur_*` DDL.

## Decisions taken up front (orchestrator)
- **A1** `tl migrate --from sqlite --to postgres` is **out of scope for this run**: it is a data-migration tool, a human gate
  in 04-gates.md §2. File it as a follow-up ticket marked `needs-human`.
- **A2** Workflow guard reads on Postgres take `SELECT ... FOR UPDATE` on the record row (LEARNINGS L-P0-I3-O2).
- **A3** Commit order = seq order on Postgres: appends take a transaction-scoped global advisory lock
  (`pg_advisory_xact_lock(<constant>)`) before reading the scope's last hash and inserting, so commits are serialised
  like SQLite's BEGIN IMMEDIATE and the seq cursor and change-feed dedupe (LEARNINGS L-P0-I4-A2) stay correct.
  Throughput tuning (per-scope locks, gap-tolerant cursors) is a later ADR.
- **A4** Parity tests skip cleanly (marker `requires_postgres`) when `TL_PG_URL` is unreachable; CI runs them.
  Each test gets an isolated schema or database (create/drop per test session) so runs don't interfere.

## Merge order and conflict owner
A → B. WS-B merges `p0/i5` after A lands and adds outbox parity tests; WS-B writes `dev/demos/P0-I5.sh` and
`docs/reports/P0-I5.md`. Merge commits only.

## Human gates
| Gate | Approver | Where recorded |
|---|---|---|
| Webhook subscription / outbox / catalog LinkML | Orchestrator under KICKOFF delegation (§18–§19) | APPROVALS.md |
| `psycopg` dependency (and `psycopg-binary` if needed) | refused (LGPL), replaced by pg8000 — ADR-0006 | APPROVALS.md (pg8000) |
| Data migration tool | Human (deferred, A1) | follow-up ticket |
