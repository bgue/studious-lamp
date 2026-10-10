# Report — P0-I7 workstream A (Ops): ledger archive, restore, backup drills

Branch `p0/i7a` (base `p0/i7`, bc02e5c). Plan: `docs/tickets/P0-I7/A-PLAN.md`. Drill report: `docs/reports/drills/2026-10-10-p0-i7a-restore-drill.md`.

## Outcome
Objective met: yes. Demo path: WS-B owns `dev/demos/P0-I7.sh`; this workstream's own check is `just drill` (`bash dev/drills/restore.sh`), run once with default parameters on 2026-10-10: every path passed.

- The ledger is sealed into signed, hash-chained segments (NDJSON, Parquet written by DuckDB, Ed25519 manifest). `tl archive verify` reports the first divergence for each of the eight `VerifyIssue` kinds; a crash between files never produces a different segment.
- `tl restore --from-archive DIR --db TARGET` rebuilds an empty SQLite file or Postgres database from the archive alone. The restored `cur_*` tables and event rows equal the originals across SQLite to Postgres and back (`tests/archive/test_restore.py`).
- SQLite: `tl backup sqlite` (online backup API) and a verified Litestream config. Postgres: a pgBackRest config and a drill against a scratch cluster. One drill script records measured RPO and RTO.

Measured by the drill (183 events at backup, 15 written after; small dataset, so RTO is a floor and includes CLI start-up):

| Path | RPO events | RPO seconds | RTO seconds |
|---|---|---|---|
| Ledger archive into SQLite | 15 | 13.9 | 9.2 |
| Ledger archive into Postgres | 15 | 13.9 | 10.5 |
| SQLite online snapshot | 15 | 13.9 | 6.6 |
| Litestream replica (loss right after the last write) | 0 | 0.0 | 8.2 |
| pgBackRest (unswitched WAL of the last batch lost) | 15 | 4.5 | 10.5 |

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| P0-I7-T01 Filesystem ArchiveStore | merged (2a0df2f) | 1 | pass first attempt |
| P0-I7-T02 `tl backup sqlite` | merged (f4236e7) | 1 | pass first attempt; hard-link `OSError` wrapped by the supervisor per ruling (452ef1e) |
| P0-I7-T03 `tl archive keygen|seal|verify` | merged (5e16010) | 1 | pass first attempt |
| P0-I7-T04 `tl restore` | merged (05f13ae) | 1 | pass first attempt; `seq=0` prints as 0 (accepted) |
| P0-I7-T05 Runbook: archive and verify | merged (92e617b) | 1 | supervisor edits after merge: business hours, `--all`, success lines, links |
| P0-I7-T06 Runbook: restore from the archive | merged (65ed8d8) | 1 | supervisor edits: Postgres verify variants, cut-over, webhook `needs_secret` |
| P0-I7-T07 Runbook: pgBackRest | merged (550b852) | 1 | supervisor edits: SQL client invocation, RTO covers verification, 30/5 run labelled |
| P0-I7-T08 Runbook: SQLite snapshots and Litestream | merged (3bfa95f) | 1 | supervisor fix: remove stale `-wal`/`-shm` before restoring a snapshot |

Merged 8 / taken over 0 / abandoned 0.

## Supervisor-built pieces (REVIEW-SUPERVISOR-PIECES)
| Piece | Commit | What | Review |
|---|---|---|---|
| S10 | abf5c2b | `tl_core.archive`: sealer (crash-idempotent), verifier (first divergence), Ed25519 `Signer`, segment encodings | reviewed once, fixes in S14 |
| S11 | 18e2bfe | `restore_events` in `tl_adapters.{sqlite,postgres}.admin`; `restore_from_archive` | reviewed once, fixes in S14 |
| S12 | d3405bc | pgBackRest and Litestream configs, `dev/drills/{restore,pgbackrest}.sh`, `drill_tools.py`, `fetch_litestream.sh`, `just drill`, `docs/templates/restore-drill.md` | fresh review pending |
| S13 | (with S12) | the drill report template and measurements | pending |
| S14 | 4fa7c6c | review fixes: missing-directory `missing_file`, sealed-prefix check for every scope, one-transaction restore with a schema check first and schema-hash warnings, `expect_last_seq` / `expect_manifest_sha256`, key file mode | re-reviewed: items 2 and 3 clean |
| S15 | ec27c11 | `verify_archive(conn, deep=True)` recomputes database hashes, compares every field, checks the tail; `verify_ledger`; `tl ledger verify`; the closing restore verify runs before the commit | pending |
| S17 | (this commit) | the dispatcher cursor starts at the restored head inside the restore transaction; the restore warning names `tl webhook replay`; the "After a restore" runbook section | pending |
| S16 | 9ec9b2b | outside WS-A scope, by orchestrator ruling: `DeliveryEngine.claim` holds back a subscription with no signing secret (pending, not sent, not dead-lettered, one log line per cycle), `tl webhook ls` shows `needs_secret`, restore returns a warning per subscription | pending |

Files: `packages/tl-core/src/tl_core/archive/`, `packages/tl-adapters/src/tl_adapters/{restore.py,_restore.py,archivestore/,sqlite/{admin,backup}.py,postgres/admin.py}`, `packages/tl-core/src/tl_core/webhooks/{delivery,queries}.py`, `packages/tl-cli/src/tl_cli/{ledger,webhook}.py`, `dev/drills/`, `dev/backup/`.

## Gates
| Gate | Result |
|---|---|
| `just check` (ruff, format, pyright strict, codegen drift, licences) | green |
| `just test` | 2686 passed |
| `just test-parity` | 1259 passed (643 s), before S17; the targeted run after S17 on both adapters passed 525 |
| Targeted runs after the webhook change, both adapters (`tests/archive`, `tests/webhooks`, `tests/contract`, `tests/parity`, tl-cli, tl-adapters) | 521 passed |
| `just drill` with default parameters | passed, report committed |
| Mutation checks | orphan-resume removed fails the crash tests; sealed-prefix check removed fails the untouched-scope test; the secret filter removed fails the two webhook tests |

## Deviations from plan
- The increment plan is `docs/tickets/P0-I7/A-PLAN.md`, mirroring `B-PLAN.md`, not `README.md`.
- WS-A changed `tl_core/webhooks` and `tl webhook ls` (S16), which is WS-B-adjacent trunk code, on the orchestrator's ruling.
- Added beyond the fanout list: `tl ledger verify` and `verify_ledger` (review ruling), `display_target`, `summarize_archive`, `archive_scopes`, `just drill`.
- The Litestream binary is fetched into the git-ignored `dev/data/tools/` and is not a dependency of any package.
- `uv.lock` changed (duckdb `1.5.5`, cryptography declared in `tl-core`). WS-B pins the same duckdb in `tl-lake`; re-resolve with `uv lock` when merging.

## Escalations and decisions
- Orchestrator: lazy duckdb import (done); the hard-link `OSError` wrap (done); restore and promoted columns use the schema in force at restore time, warn when its hash differs from the ledger's (done); the missing-secret webhook hold (done, S16).
- Dependencies, with licences: `duckdb==1.5.5` (MIT), `cryptography` (Apache-2.0/BSD, already in the tree), apt `pgbackrest` 2.50 (MIT), Litestream v0.3.13 binary (Apache-2.0).
- Ruled and done (S17): after a restore the webhook dispatcher cursor starts at the restored head, so history is not queued again; `tl webhook replay ID --from-seq N --to-seq M` covers a range a receiver may have missed (named in the warning and the runbook).

## Learnings
Appended L-P0-I7-A1 to A12 to `docs/memory/LEARNINGS.md`: promoted columns on restore (A1), crash-safe sealing (A2), `types.py` module name (A3), sibling tickets and fixtures (A4), egress and downloads (A5), three review rules (A6), deep database verification (A7), drill mechanics (A8), webhook secrets after restore (A9, A10), WAL sidecars and runbook tickets (A11), dispatcher cursor after a restore (A12). Implementer proposals declined: none; the `^ *```` checker note was folded into A11.

## Docs
- Runbooks: `docs/runbooks/{ledger-archive-and-verify,restore-from-archive,pgbackrest-restore,sqlite-backup-and-litestream}.md`; index and `webhook-operations.md` updated.
- READMEs and AGENTS.md: `packages/tl-core`, `packages/tl-adapters`, `packages/tl-cli`; root `AGENTS.md` "Where things go".
- Template: `docs/templates/restore-drill.md`. Ticket reports: `docs/reports/P0-I7/P0-I7-T01.md` to `T08.md`.

## Follow-ups filed
- Human: production key custody (KMS, HSM), retention classes and object lock for the archive (brief 24.3).
- Not exercised by the drills: pgBackRest point-in-time recovery, incremental and differential backups, the encrypted S3 repository, a MinIO Litestream replica.
- The `tl webhook`, `tl file` and root `--db` take a SQLite path only; a Postgres operator needs the API (P0-I4) for those.
- The lake can rebuild from segments (`events.parquet` has the bronze shape); WS-B owns that path.

## Cost notes
Eight implementer tickets, each passed review first time; no takeover. Supervisor effort went mainly into the sealer, verifier and restore (S10 to S15), which had two review rounds, and the drills.
