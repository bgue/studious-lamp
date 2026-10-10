# Restore drill — dev container (P0-I7 WS-A), 2026-10-10

Status: passed
Script: `dev/drills/restore.sh` at commit e73c022. Run by: root. Brief: §24.3, §24.4 (restore drills: quarterly in staging and after major upgrades; record measured RPO and RTO).

The dataset is synthetic. The script writes this file from its measurements, so fill nothing in by hand; `TL_DRILL_ENV` and `TL_DRILL_OPERATOR` name the environment and the person.

## What was exercised
| Path | What it proves | Result |
|---|---|---|
| Ledger archive into SQLite | The signed archive alone rebuilds a SQLite ledger and its `cur_*` tables | pass |
| Ledger archive into Postgres | The same archive rebuilds a Postgres ledger (scratch database `tl_drill_20261010t050537_19402`) | pass |
| SQLite online snapshot | `tl backup sqlite` output is a usable ledger | pass |
| Litestream replica | A continuously replicated copy restores after the file is lost | pass |
| pgBackRest full backup plus WAL | A scratch Postgres cluster survives loss of its data directory | pass |

A path that was skipped says why under Findings. The shared cluster and its `tl_test` database are never used.

## Dataset
| Item | Value |
|---|---|
| Events when the archive was sealed and the snapshot taken | 183 |
| Events written after that, before the loss | 15 |
| Newest event when the loss was simulated | seq 198, recorded 2026-10-10T05:05:56.737775+00:00 |
| Ledger archive | 4 segments, up to seq 183 |
| Schema packages | `TL_SCHEMA_DIR=schema/fixtures` |

## Measured RPO and RTO
- **RPO events**: events committed after the newest event the recovered database holds, when the loss happened.
- **RPO seconds**: the recorded time of the newest lost event minus that of the newest recovered event, the length of history lost.
- **RTO seconds**: from the start of the restore until the restored database passed `tl ledger verify` and accepted a new event.
- A continuous path (Litestream, WAL archiving) is measured with the loss right after the last write (about one command's delay), so its RPO is close to the worst case, not the best.
- Every timing includes the start-up of the `tl` and helper commands (a second or two each); it is a floor for an operator typing the same commands.

| Path | RPO events | RPO seconds | RTO seconds | Brief target | Met |
|---|---|---|---|---|---|
| Ledger archive into SQLite | 15 | 13.91 | 9.16 | archive RPO <= 15 min, RTO <= 1 h | yes |
| Ledger archive into Postgres | 15 | 13.91 | 10.45 | archive RPO <= 15 min, RTO <= 1 h | yes |
| SQLite online snapshot | 15 | 13.91 | 6.56 | database RPO <= 5 min, RTO <= 1 h | yes |
| Litestream replica | 0 | 0.00 | 8.17 | database RPO <= 5 min, RTO <= 1 h | yes |
| pgBackRest | 15 | 4.48 | 10.47 | database RPO <= 5 min, RTO <= 1 h | yes |

The drill dataset is small, so RTO here is a floor: restore time grows with the number of events (the archive path replays every event) and with database size (pgBackRest). Compare the
trend between drills, not one number with a target. pgBackRest `archive_timeout` was 15 s, which bounds the unswitched WAL it can lose; the full backup took
3.76 s and the restore command 0.71 s.

## Verification
| Check | Result |
|---|---|
| `tl archive verify` on the archive, with the public key | pass (seq 1..183, recorded last seq and manifest present) |
| `tl archive verify --deep --db` on each restored database (every field equal to the archive) | pass on every restored database |
| `tl ledger verify` on each restored database (hashes recomputed, chains intact) | pass on every restored database |
| Restored `cur_*` tables and events equal the original at the backup point (digest `events=21be1692d71b31d6 tables=7fdcd31c9a98eb64`) | pass (archive and snapshot paths) |
| A new event is accepted by each restored database | pass |
| A tampered copy of the archive is refused with the first divergence | pass: divergence: file_hash segment=000000000061-000000000120 seq=61: events.ndjson differs from its hash |

## Timeline
| Step | Seconds |
|---|---|
| Populate, seal, snapshot | 17.48 |
| Restore from archive into SQLite | 14.21 |
| Restore from archive into Postgres | 16.87 |
| Restore from snapshot | 11.75 |
| Restore from Litestream | 11.57 |
| pgBackRest (whole drill, including cluster create and drop) | 63.20 |

## Findings
- none

## Follow-ups
- Production key custody, retention classes and object lock are human decisions (brief 24.3) and are not exercised by this drill.
- Record the date and the commit of the next drill: quarterly in staging, and after every major upgrade.
