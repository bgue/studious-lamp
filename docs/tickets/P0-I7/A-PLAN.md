# Increment plan — P0-I7 workstream A (Ops): ledger archive, restore, backup drills

Status: in-progress
Supervisor session: 2026-10-10
Brief sections: §24.3 (backup), §24.4 (restore), §24.5 (tampering suspicion); ADR-0002 and its addendum; fanout `docs/tickets/P0-I7/FANOUT.md` (D1 to D6)
Branch: `p0/i7a` (base `p0/i7`, bc02e5c)

## Objective
The ledger is sealed into signed, hash-chained archive segments that are independent of the database. `tl archive verify` reports the first divergence. `tl restore
--from-archive DIR --db URL` rebuilds an empty SQLite or Postgres database from the archive alone, and the restored `cur_*` tables equal the originals. SQLite has an online
snapshot (`tl backup sqlite`) and a Litestream config. Postgres has a pgBackRest config and a drill against a scratch cluster. One drill script records measured RPO and RTO.

## Demo
WS-B owns `dev/demos/P0-I7.sh`. This workstream's own check is the drill (`bash dev/drills/restore.sh`), which prints a filled `docs/templates/restore-drill.md`.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S10 | `tl_core.archive`: sealer (crash-idempotent), verifier (first divergence per `VerifyIssue` kind), Ed25519 `Signer`, segment encodings (NDJSON, Parquet by DuckDB) | Hash-chain integrity and crash safety; migration-like data path | orchestrator | done (abf5c2b) |
| S11 | `restore_events` in `tl_adapters.{sqlite,postgres}.admin` and `tl_adapters.restore.restore_from_archive` | Writes events outside `Ledger.append` (D1); data conversion path | orchestrator | done (18e2bfe); review fixes in S14 |
| S14 | Review fixes to S10 and S11: missing-directory handling, sealed-prefix check for every scope, one-transaction restore with a schema check first and schema-hash warnings, `--expect-last-seq`/`--expect-manifest`, key file mode | Same pieces | orchestrator (short re-review of items 2 and 3) | done |
| S12 | pgBackRest config and `dev/drills/pgbackrest.sh` against a scratch cluster; Litestream config | Needs sudo, a scratch cluster and measurements; not ticket-shaped | reviewer | planned |
| S13 | `dev/drills/restore.sh` and `docs/templates/restore-drill.md` | Measures RPO and RTO across SQLite, Postgres and archive | reviewer | planned |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I7-T01 | Filesystem ArchiveStore (write-once) | haiku | S10 | merged (2a0df2f) | passed review first attempt |
| P0-I7-T02 | `tl backup sqlite` and `backup_database` | haiku | none | merged (f4236e7) | passed review first attempt; hard-link OSError wrapped by supervisor (452ef1e) per ruling |
| P0-I7-T03 | `tl archive keygen\|seal\|verify` | haiku | T01, S10 | ready | |
| P0-I7-T04 | `tl restore --from-archive` | haiku | T01, S11 | ready | |
| P0-I7-T05 | Runbooks: archive and verify, restore from archive | haiku | T03, T04 | draft (batch 3) | |
| P0-I7-T06 | Runbooks: pgBackRest restore, SQLite backup and Litestream | haiku | S12, T02 | draft (batch 3) | |

## Order of work
1. Plan, S10, S11 (done). Tickets T01 and T02 (batch 1), because nothing else they need is missing.
2. Batch 2 after T01 merges: the two CLI tickets, which need a working store. S12 and S13 are built meanwhile.
3. Batch 3 after the CLIs and drills exist: runbooks, written from commands that were actually run (L-P0-I4-B7).
4. Package READMEs and AGENTS.md, learnings, `just check`, `just test`, `just test-parity`, report.

## Risks and escalation triggers
- DuckDB Parquet bytes could differ between runs. Sealing writes the Parquet at most once per segment and a retry accepts an existing file only after reading it back and
  comparing rows, so a crash never needs identical bytes. A test seals twice into separate stores and compares them.
- The promoted pset columns of `cur_core_record` depend on the schema packages in force at restore time (found by the restore test). Restore adds them from the process-wide schema
  provider. Recorded as a learning and in the restore runbook.
- uv.lock: this workstream adds `duckdb==1.5.5` (MIT) and `cryptography` (Apache-2.0/BSD) to `tl-core`; WS-B adds the same pin to `tl-lake`. The later merge resolves `uv.lock` with `uv lock`.
- Stop with BLOCKED on a 03 §7 interface change, or any 04-gates §2 item beyond the delegated dependencies.

## Blocked / Decision
(none yet)
