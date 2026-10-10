# Report — P0-I5 WS-A Postgres adapter and parity suite

Written 2026-10-10. Branch `p0/i5a` (integration branch `p0/i5`, trunk `claude/wizardly-allen-m2v96s`). Plan: `docs/tickets/P0-I5/README-A.md` (decisions D1 to D15). Not merged into `p0/i5` or the trunk.

## Outcome
Objective met: yes. Every behaviour that the adapter, projector, service, query, change-feed and file tests cover runs on SQLite and on PostgreSQL 16 from one set of tests, and both are green. Demo path (WS-A part): `just test-parity`, then `uv run pytest packages/tl-adapters/tests/test_postgres_ledger.py -q`; verified on this container. The webhook demo belongs to WS-B.

What exists now:
- `tl_adapters.postgres`: engine, ledger, unit of work, `PostgresUowFactory`, `NotifyListener` (LISTEN/NOTIFY), admin helpers. `tl_adapters.db` picks the adapter from a SQLite path or a `postgresql://` URL.
- Write transactions take one advisory lock first (commit order equals `seq` order; guard reads are current), pin `READ COMMITTED`, and a wait past 10 s raises `LockTimeoutError`; deadlocks raise `RetryableTransactionError`. `seq` is gap-free; the per-scope hash chain is byte-identical to SQLite's; triggers forbid UPDATE, DELETE and TRUNCATE.
- Rows look the same to `tl_core` on both adapters (canonical JSON text, ISO UTC timestamps, 0/1 booleans, int sums).
- Generator: Postgres `TEXT` is `COLLATE "C"` (sorting matches SQLite whatever the server locale) and LinkML `float` is `DOUBLE PRECISION`.
- Parity fixtures in the root `conftest.py` (`--adapters`, `new_db`, `db`, `new_engine`, `dialect`, `pg_db`), `just test-parity`, a CI job with a Postgres service container, a runbook, the ADR-0006 licence gate in `just check`.
- Driver: `pg8000` (BSD-3-Clause). psycopg was refused by the orchestrator (LGPL, ADR-0006).

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| T01 record command and query tests | merged | 1 | |
| T02 pset command and service tests | merged | 1 | |
| T03 schema events, required files, can/cannot | merged | 1 | one INSERT literal `0` to `FALSE` |
| T04 numbering and property tests | merged | 1 | Hypothesis tests call `new_db()` per example |
| T05 workflow and expected-links tests | merged | 1 | |
| T06 file service tests | merged | 1 | |
| T07 reconcile and change-feed integration tests | merged | 1 | |
| T08 query-language tests | merged | 1 | ticket said 3 pure tests, the file has 4; total of 10 right |
| T09 projector unit tests | merged | 1 | test renamed `test_ddl_creates_table_and_is_idempotent` |
| T10 generated DDL executes and stores alike | merged | 1 | engine fixture is function-scoped (needs `new_engine`) |
| T11 CI parity job | merged | 1 | unverified until it runs on a GitHub runner |
| T12 Postgres runbook and compose service | merged | 1 | dev-up start path, the sweep and the DROP command were not exercised by the implementer |
| T13 licence gate (ADR-0006) | merged | 1 | `licences ok` for 148 distributions |
| T99 `tl migrate --from sqlite --to postgres` | not built | | `needs-human` draft (A1) |

Taken over: none. Abandoned: none (T99 is deferred by decision). 13 of 13 built tickets merged, all on the first review.

Supervisor-built pieces S1 to S8 (README-A) were reviewed by two fresh reviewers (S1/S3/S6: pass; S2/S4/S5: minor changes, fixed; S8 after the pg8000 swap: pass).

## Gates
| Gate | Result |
|---|---|
| `just check` | exit 0 on the merged tip; ends with `licences ok` |
| `just test` | 2282 passed |
| `just test-parity` | 1214 passed, 1663 deselected, no skips (Postgres reachable, `TL_REQUIRE_POSTGRES=1`); 11 minutes on a heavily loaded container |
| `just test-tui` | not applicable (no TUI change) |
| Schema classification | not applicable: no `schema/**` change |
| Licence gate | in `just check` |

## Deviations from plan
- Driver: the plan named `psycopg`; the orchestrator refused it (LGPL, a human gate) and approved `pg8000`. The adapter was ported mid-increment (README-A D14); hash chain and behaviour unchanged.
- Parity selection by marker and `--adapters` instead of `pytest tests/parity -p sqlite/-p postgres` (D7); the orchestrator amended `03` §3 on the trunk.
- `events.seq` is `MAX(seq)+1` under the lock, not an identity column (D3); `events.payload` is TEXT, not JSONB (D4).
- Production code needed few changes. The dialect bugs found were `REAL` precision, text collation (server locale), SQLAlchemy reflection breaking on collated columns and returning JSON as text, a negative zero stored differently, and pg8000 reporting only unique violations as `IntegrityError`. Almost every other failure in the first parity run was test-side raw SQL (L-P0-I5-A4).
- Not done, by decision: a unique constraint on `cur_files (record_id, slot, revision)` (D11); the `tl` CLI, TUI and API still open SQLite paths (D12).

## Escalations and decisions
- Orchestrator rulings: psycopg refused, pg8000 approved; S1/S3/S6 review rulings (READ COMMITTED pin, `LockTimeoutError`, reusable unit of work, JSON edge cases documented, reconnect test); S2/S4/S5 rulings (ASCII-only `LOWER`, ICU test honours `TL_REQUIRE_POSTGRES`, SIGTERM cleanup and sweep); S8 rulings (`RetryableTransactionError`, negative zero, pid in database names, pooled factory, notes).
- No *Blocked* entries in any ticket.

## Needs human
- `docs/tickets/P0-I5/T99-migrate-sqlite-to-postgres.md`: the migration tool is a data-migration job (`04-gates.md` §2). It needs a named approver and an ADR before anyone builds it.
- T11 is unverified until the `parity` job runs on a GitHub runner (the default `postgres:16` image uses an `en_US.utf8` locale, which the `COLLATE "C"` columns are designed for).

## Not verified locally
- The compose `postgres` service was written but never started (no Docker daemon, ADR-0002); it shares host port 5432 with the native cluster (runbook note).
- The runbook's `just dev up` start path, the stale-database sweep command and the manual `DROP DATABASE` were not exercised by the T12 implementer; the sweep and SIGTERM cleanup are covered by tests.

## Learnings
Appended to `docs/memory/LEARNINGS.md`: L-P0-I5-A1 to A10 (advisory lock and gap-free seq; driver loaders and no reflection; collation and double precision; test SQL rules; fixture scoping and orphan databases; reference-conversion triage; licence check before adding a dependency; pg8000 differences; parity run times; docstring and ticket-wording rules).
Implementer proposals declined, with reasons: the `sed -i` then `Edit` "modified since read" friction and the `UV_NATIVE_TLS` warning (harness and environment noise, the latter already L-P0-SETUP-6); the harmless `dev up: skipped MinIO` line; T01's note that boolean assertions pass because `False == 0` (the adapter returns 0/1 by design, L-P0-I5-A2); T10's module-fixture scope note (already L-P0-I5-A5).

## Docs
- `packages/tl-adapters/README.md` and `AGENTS.md` rewritten for Postgres, configuration and rules; `packages/tl-core/README.md` lists the new errors.
- Runbook `docs/runbooks/postgres-local-setup.md` (T12, with the compose-port note added by the supervisor).
- README-A is the plan, decision log and ticket table; the licence gate is described in ADR-0006 (trunk).

## Follow-ups filed
- `T99` migration tool (needs-human).
- Switch the `tl` CLI, TUI embedded mode and the API to `tl_adapters.db` so they can run on a Postgres URL (D12).
- WS-B: add `SqliteUowFactory` dispatch to `tl_adapters.db` (a `make_uow_factory`) once it merges; the Postgres side is `PostgresUowFactory`; add outbox parity tests with the `new_db` fixtures.
- The `cur_files (record_id, slot, revision)` unique constraint after a service review (D11).
- Parity run time (about 11 minutes under load): consider running the Hypothesis property tests on SQLite only in the PR job and on both nightly, if the CI budget needs it (L-P0-I5-A9).

## Cost notes
Three supervisor rounds with relay (plan and core, driver swap and review fixes, batches 2 and 3). 13 implementer tickets, 13 first-pass reviews, 5 independent reviews of supervisor pieces. The reference conversion (a scratch worktree, `/home/user/wt/p0-i5a-refs`) was built once and removed from use after the merges; it can be deleted.
