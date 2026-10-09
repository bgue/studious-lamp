# Increment plan — P0-I5 WS-A Postgres adapter and parity suite

Status: in-progress
Supervisor session: 2026-10-09
Brief sections: §5.1–§5.4 (ledger, hash chain, projections, DDL), §14 (Postgres is production), §15 (portability), `03` §6 and §10, `04` §1
Branch: `p0/i5a` (integration branch `p0/i5`; trunk `claude/wizardly-allen-m2v96s`). Ticket branches `p0/i5a-t<nn>-<slug>`.
Fanout plan: `docs/tickets/P0-I5/FANOUT.md` (contracts C1 to C3 and decisions A1 to A4 are binding here).

## Objective
Everything that runs on SQLite runs identically on PostgreSQL 16. The Postgres ledger appends under a transaction-scoped advisory lock (commit order
equals `seq` order; the per-scope hash chain is byte-identical to SQLite's; triggers forbid UPDATE, DELETE and TRUNCATE), the Postgres unit of work runs
the projector registry exactly as SQLite's does (C2), and DDL comes from the generator (C3). One set of tests, parametrised by an `adapter` fixture,
exercises the adapter, projector, service, query, change-feed and file-service code on both databases; `just test-parity` runs it and fails (does not skip)
without Postgres; CI runs it against a Postgres service container. `LISTEN/NOTIFY` gives the change-feed poller a wake-up hook. A SQLite-to-Postgres
migration tool is out of scope (A1) and filed as a `needs-human` draft (`T99`).

## Demo
WS-B owns `dev/demos/P0-I5.sh`. WS-A alone is shown by:
```
sudo pg_ctlcluster 16 main start        # if pg_isready -h localhost fails
just test-parity                        # parity-marked tests on sqlite and postgres, plus the Postgres-only tests
uv run pytest packages/tl-adapters/tests/test_postgres_ledger.py -q    # lock, hash identity, wake-ups, commit order
```
Expected: all green, `TL_REQUIRE_POSTGRES=1` set by the recipe, no skips.

## Design decisions (supervisor; none changes a frozen contract in `03` §7)
| # | Decision | Why |
|---|---|---|
| D1 | Every write transaction takes `pg_advisory_xact_lock(<constant>)` as its first statement (`postgres/engine.py::write_tx`); `append_in` takes it again (free, explicit). `lock_timeout` is 10 s. Readers are `REPEATABLE READ` read-only snapshots and never wait | Fanout A3. It is the analogue of `BEGIN IMMEDIATE`: commit order equals seq order (LEARNINGS L-P0-I4-A2: the poller needs no lag window) and every read inside a write transaction is current |
| D2 | Workflow guard reads need no `SELECT ... FOR UPDATE` | Fanout A2 is satisfied more strongly by D1: the lock is taken before the first read, so a guard cannot see stale links. `test_a_write_transaction_reads_what_the_previous_writer_committed` proves it (L-P0-I3-O2) |
| D3 | `events.seq` is a plain `BIGINT` primary key assigned as `MAX(seq)+1` under the lock, not an identity column | An identity burns a value on rollback; SQLite's `seq` is gap-free and a gap-free feed is simpler for pollers and archive segments. A writer that bypassed the lock collides on the key instead of reordering |
| D4 | `events.payload` is `TEXT`; `recorded_at` / `effective_at` are `TIMESTAMPTZ`; hash input is identical to SQLite's | JSONB re-renders numbers (`1e22`), so a stored event could no longer be re-hashed. A generated JSONB column can be added when SQL-side payload queries need one |
| D5 | The Postgres driver is configured so rows look like SQLite's to `tl_core`: JSON columns as canonical compact text, `timestamptz` as `iso_utc` strings, booleans as 0/1, `SUM` of integers as ints (`engine.py` loaders) | Orchestrator note on `_envelope`'s `json.loads`: option two (adapter-side loaders). `tl_core` stays neutral, no `isinstance` checks, text comparisons in tests hold on both databases. Cost: SQLAlchemy reflection (`inspect().get_columns`) breaks on Postgres, so core uses `promoted.table_columns` (a zero-row `SELECT *`) |
| D6 | The generator emits `TEXT COLLATE "C"` on Postgres and maps LinkML `float` to `DOUBLE PRECISION` | Postgres sorts text by the server locale (`en_US.utf8` in the default image) and SQLite bytewise: `ORDER BY title` differed. `REAL` is 4 bytes on Postgres and rounded pset numbers. Tests: `test_postgres_collation.py` (ICU database), `test_generated_ddl_parity.py` (T10) |
| D7 | `tl_adapters.db` picks the adapter from the target (a SQLite path or a `postgresql://` URL); tests use the root-conftest fixtures `new_db`, `db`, `new_engine`, `dialect`, selected with `--adapters` and marked `parity` / `requires_postgres` | One test body, two databases. Deviation from `03` §3 ("`pytest tests/parity -p sqlite` and `-p postgres`"): parity tests stay beside the code they test, selected by marker; `tests/parity/` holds only the fixture self-check |
| D8 | Each pytest session creates a throw-away database `tl_pytest_<hex>` and each test a schema `tl_t_<hex>` in it; falls back to schemas in the given database when `CREATE DATABASE` is refused | Fanout A4 plus concurrent agents: separate databases also mean separate ledger locks |
| D9 | `NOTIFY tl_events` carries `<schema>:<last seq>`; `NotifyListener` sets a `threading.Event`; `ChangePoller(wake=...)` ends its wait early | Brief §14. Cursor reads stay authoritative; a lost or spurious wake-up costs one poll |
| D10 | `PostgresUowFactory` has the call shape of WS-B's `SqliteUowFactory` (`factory()` / `factory(readonly=True)`, `dispose()`), one pooled engine | Orchestrator note 1: the webhook workers are written once for both adapters |
| D11 | Not done: a unique constraint on `cur_files (record_id, slot, revision)` (P0-I4 follow-up) | It is a `schema/**` change, and a rejected upload followed by a re-upload may legitimately reuse a revision number, so the constraint needs a service review; the ledger lock already makes duplicates impossible. Left as a follow-up |
| D12 | `tl` CLI, TUI embedded mode and the API keep opening SQLite paths | `tl_cli` / `tl_tui` import `tl_adapters.sqlite.uow` directly; switching them to `tl_adapters.db` is mechanical but outside this increment's exit criteria. Follow-up |
| D13 | `LOWER()` folds ASCII only on both adapters: generated Postgres `TEXT` is `COLLATE "C"`, whose ctype is ASCII-only, so non-ASCII case-insensitive matching behaves identically | Pinned by `tests/parity/test_text_folding.py`; documented in `packages/tl-adapters/README.md`, with the JSONB edge cases (1e16 and above read back as integers, `-0.0` as `0.0`, NUL rejected) |
| D14 | The Postgres driver is pg8000 through `postgresql+pg8000`. `postgresql://` URLs are accepted everywhere and rewritten inside `postgres/engine.py`; a schema is selected with the startup parameter `search_path` (from the URL's `options=-csearch_path=...`, which `admin.schema_url` writes). Result coercions are `register_in_adapter` functions; class-23 SQLSTATEs are re-raised as `IntegrityError` (pg8000 does that only for unique violations); `NotifyListener` polls `conn.notifications` after a `SELECT 1` every 50 ms | Orchestrator ruling: psycopg is LGPL. Hash chain and all ledger behaviour are unchanged |

## Supervisor-built pieces (in order)
REVIEW-SUPERVISOR-PIECES: S1 to S6 below are Sonnet-authored by rule (ledger append, hash chain, transaction isolation) and need orchestrator or human review before WS-A is merged into `p0/i5`.

| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | `tl_adapters.postgres` (`engine`, `ddl`, `ledger`, `uow`, `admin`), shared `_unit.py` / `_publish.py`, `tl_adapters.db` dispatch | Ledger append, advisory-lock serialisation, hash chain, UoW; refactors the SQLite UoW onto the shared base | Orchestrator | built; 32 ledger + 26 UoW parity tests; mutation (drop the lock) fails 5 Postgres tests |
| S2 | Parity fixtures in root `conftest.py` (`adapter`, `new_db`, `db`, `new_engine`, `dialect`, `pg_db`), `just test-parity`, `tests/parity/` self-check | Fixture design is the contract every ticket uses | Orchestrator | built |
| S3 | `postgres/notify.py` `NotifyListener`; `ChangePoller(wake=...)` | Threads and a core engine class | Orchestrator | built; 3 poller tests + 4 wake-up tests |
| S4 | Generator: `collated()`, float to `DOUBLE PRECISION`; regenerated DDL; golden file and `test_postgres_differs_only_in_the_documented_types` updated; `promoted.table_columns` replaces reflection | Cross-dialect DDL generator is Sonnet-authored by rule (`01-tiers` §3) | Orchestrator | built |
| S5 | `test_postgres_ledger.py` (15), `test_postgres_collation.py` (2), `test_postgres_factory.py` (2) | They prove S1, S3, S4 | Orchestrator | built |
| S6 | `PostgresUowFactory` | Contract with WS-B | Orchestrator | built |
| S7 | Reference implementation of T01 to T11 kept outside the repo in `/home/user/wt/p0-i5a-refs` until the tickets merge (takeover path, and where the acceptance counts come from) | Verification | — | built; sqlite+postgres: 2300+ passed |

## Tickets
Haiku-ability (`01-tiers` §6), checked for every row: (1) at most 6 files to read (the files to convert, `conftest.py`, `db.py`); (2) all interfaces are on the base
branch (fixtures and `tl_adapters.db` are committed); (3) acceptance is a pytest count, not prose; (4) diff well under 400 lines over at most 5 files
(measured on the reference: 30 to 140 changed lines per file); (5) no row of the Sonnet-authored table (tests only); (6) no `schema/**`, migration, dependency or
public-interface change; (7) a reviewer verifies from the diff plus the commands. T08 touches five files (the limit) and T10 creates one.

| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | Record command and query tests on both adapters | H | — | ready | |
| T02 | Pset command and service tests on both adapters | H | — | ready | |
| T03 | Schema events, required files, project can/cannot tests on both adapters | H | — | ready | |
| T04 | Numbering tests and property tests on both adapters | H | — | ready | |
| T05 | Workflow engine and expected-links tests on both adapters | H | — | ready | |
| T06 | File upload service tests on both adapters | H | — | ready | |
| T07 | Reconciliation and change-feed integration tests on both adapters | H | — | ready | |
| T08 | Query-language tests on both adapters | H | — | ready | |
| T09 | Projector unit tests on both adapters | H | — | ready | |
| T10 | Generated DDL executes and stores values alike on both dialects | H | — | ready | |
| T11 | CI parity job with a Postgres service container | H | — | ready | |
| T12 | Runbook for local Postgres and the compose service | H | — | ready | |
| T99 | `tl migrate --from sqlite --to postgres` | S | WS-A merged | draft, needs-human | filed, not built (A1) |

## Order of work
1. Round 1 (done): S1 to S7; the reference run showed production code was already close to portable: the two real dialect bugs were `REAL` precision and text collation, plus
   reflection; every other failure was test-side raw SQL (integer literals in boolean columns, `?` placeholders, invalid timestamps).
2. Batch 1: T01 to T04 (service tests). Batch 2: T05 to T08. Batch 3: T09 to T12. Disjoint *Allowed paths* inside each batch; the whole set is disjoint.
3. After each batch: merge passed tickets (merge commits), run `just check`, `just test`, `just test-parity`; take over two-strikes tickets from the reference.
4. Last round: README and AGENTS.md of `tl-adapters`, learnings, report `docs/reports/P0-I5-A.md`; DONE.

## Risks and escalation triggers
- A converted test that fails on Postgres for a production reason (the implementer stops under *Blocked*): the supervisor fixes it in `tl_adapters` or the generator.
- Concurrent agents share the Postgres server: a killed run leaves `tl_pytest_*` databases (runbook T12). Per-session databases keep the ledger lock private.
- Batch concurrency is two agents at a time (L-P0-SETUP-9), so batches take about twice as long as the spec's four-wide dispatch.
- Escalate to the orchestrator for: a change to a frozen interface in `03` §7, a `schema/**` change (none is planned), or a second failed review of S1.

## SCHEMA_APPROVALS
None. WS-A changes no file under `schema/**`; the generator change (D6) regenerates only `packages/tl-schema/src/tl_schema/generated/ddl/postgres/`.
New dependency: `pg8000>=1.31` (BSD-3-Clause; pulls `scramp` MIT-0, `asn1crypto` MIT, `python-dateutil` Apache-2.0/BSD) in `packages/tl-adapters/pyproject.toml`, `uv.lock` updated. Approved by the orchestrator, logged in `docs/reports/APPROVALS.md` on the trunk. `psycopg` was refused: it is LGPL-3.0, a copyleft dependency, which is a human gate (`04-gates.md` §2).

## Blocked / Decision
(none)
