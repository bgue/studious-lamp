# Fanout plan: P0-I7 (backup, ledger archive, restore, DuckLake v0)

Status: draft. Starts after P0-I5 (Postgres adapter) is on the trunk. Both workstreams start together.
Orchestrator session: 2026-10-09
Brief sections: §24.3–§24.5, §28.1–§28.4, §11.3 (`lake_query`); ADR-0002 and its addendum (environment probes)

## Objective
The ledger is sealed into signed, hash-chained archive segments that are independent of the database. The ledger can
be verified against them and rebuilt from them alone. SQLite and Postgres both have a working backup and restore
drill. An incremental DuckLake copy (bronze events, silver current state) answers DuckDB queries and a read-only
`lake_query` MCP tool, and states which ledger seq range it reflects.

## Exit criteria
- [ ] `tl archive keygen|seal|verify` implement the contract in `tl_core/archive/types.py`. A crash between files never leaves a different segment. `verify` reports the first divergence (`VerifyIssue`).
- [ ] `tl restore --from-archive DIR --db URL` works into an empty SQLite or Postgres database. It inserts events verbatim through `tl_adapters.<dialect>.admin.restore_events`, then rebuilds projections. A test shows that restored `cur_*` tables equal the originals.
- [ ] SQLite backup: an online backup API snapshot (`tl backup sqlite`), plus Litestream config committed as documentation. Fetch the Litestream binary once, per the ADR-0002 download rule; if that fails, the drill uses the snapshot path only.
- [ ] Postgres backup: pgBackRest installed with apt (2.50, MIT) and a local repo configured for the native cluster. The drill script takes a full backup, damages a scratch database, restores it, and verifies it against the archive. Everything runs against a dedicated scratch cluster or database, never the shared `tl_test`.
- [ ] A restore drill script and report template (`dev/drills/restore.sh`, `docs/templates/restore-drill.md`) that records measured RPO and RTO. Runbooks: archive and verify, restore from archive, pgBackRest restore.
- [ ] `tl-lake` package (03 §1). It bootstraps DuckLake through `duckdb_extensions.import_extension('ducklake')`, with duckdb pinned to the extension wheel's version (L-P0-I5-O2).
  - Catalog: a DuckDB file under `dev/data/lake/`.
  - Data: Parquet under `dev/data/lake/data/`.
- [ ] `tl lake sync` is incremental by seq. Each sync commits one DuckLake snapshot, and `_tl_sync` records `(snapshot_id, first_seq, last_seq, synced_at)` in the same transaction.
  - Bronze: `events`.
  - Silver: `cur_core_record`, `links` and `pset_values`, from the generated schema, including promoted pset columns.
  - A full rebuild equals the incremental result.
- [ ] `lake_query` MCP tool: read-only, a SELECT/WITH allow-list parsed by DuckDB (no DDL or DML, no ATTACH, INSTALL, LOAD, COPY or PRAGMA), a row limit, an allowed catalog only, and every call logged.
- [ ] `just demo P0-I7`: seal, verify, tamper with a copy, and verify again, which finds the first divergence. Then restore from the archive into a fresh database, run lake sync, and run a DuckDB query that shows its "as of seq" line.

## Workstreams
| WS | Name | Branch | Base | Supervisor builds | Implementer tickets (summary) |
|---|---|---|---|---|---|
| A | Ops | `p0/i7a` | `p0/i7` after P0-I5 is on the trunk | archive sealer and verifier, Signer, the `restore_events` admin functions (both dialects), the restore orchestration | fs ArchiveStore; `tl archive` and `tl restore` CLI; `tl backup sqlite`; Litestream config; pgBackRest config and drill script; report template; runbooks |
| B | Lake | `p0/i7b` | `p0/i7` after P0-I5 is on the trunk | DuckLake bootstrap, sync engine with the `_tl_sync` watermark, silver mapping from the generated schema | bronze loader; silver tables; `lake_query` tool and its guard tests; demo queries; README |

## Shared contracts
- `packages/tl-core/src/tl_core/archive/types.py`, committed on `p0/i7`: the segment layout, `SegmentManifest`, `ArchiveStore`, `VerifyIssue`, and the service signatures.
- The lake watermark is DuckLake table `_tl_sync(snapshot_id BIGINT, first_seq BIGINT, last_seq BIGINT, synced_at TIMESTAMP)`. A sync reads events with `seq > max(last_seq)`. Bronze rows carry `seq` and are never updated. A silver row is replaced when its stream changes.
- Bronze `events` has the same columns as `events.parquet` in an archive segment, so a lake rebuild can load archive segments directly (§28.2).

## Orchestrator decisions
| # | Decision |
|---|---|
| D1 | Restore inserts events verbatim through a per-dialect admin function, not `Ledger.append`. 03 §7 is unchanged. `restore_events` refuses a non-empty `events` table. |
| D2 | Archive signing uses Ed25519 from `cryptography` (Apache-2.0/BSD; already in the tree through mcp and pyjwt). The dev key lives in `dev/data/` and is git-ignored. Production key custody (KMS, HSM) is a later decision, recorded as a follow-up. It is not built here. |
| D3 | Parquet is written by DuckDB, so there is no pyarrow dependency. Payloads are stored as canonical JSON text, so hashes re-verify from Parquet. |
| D4 | The ArchiveStore is independent of the record ObjectStore (a different root, write-once). Object lock and WORM in production come later. |
| D5 | pgBackRest and the drill run only against a scratch cluster or database created by the drill script. The shared `tl_test` database is never touched. |
| D6 | `lake_query` guard: parse with DuckDB's `json_serialize_sql` or a statement-type check, and allow only SELECT. The tests include stacked statements, `ATTACH`, `COPY`, `read_csv` on arbitrary paths and `PRAGMA`. File-reading table functions are refused, except on lake tables. |

## Merge order and conflict owner
A → B. B writes `dev/demos/P0-I7.sh` and `docs/reports/P0-I7.md`. Merge commits only.

## Human gates
| Gate | Approver | Where |
|---|---|---|
| Dependencies `duckdb==1.5.5`, `duckdb-extensions`, `duckdb-extension-ducklake` (MIT); apt `pgbackrest` (MIT); Litestream binary (Apache-2.0) | Orchestrator under KICKOFF delegation, licences checked (ADR-0006) | APPROVALS.md |
| Production key custody, retention classes, object lock | Human | Follow-up in the report |

## Risks
- DuckLake is young (R13). Pin versions. If the extension misbehaves, fall back to plain Parquet plus a DuckDB views catalog and record it as a deviation.
- pgBackRest needs to run as the postgres user and needs archive_command settings. Keep the drill's config changes on the scratch cluster only.
