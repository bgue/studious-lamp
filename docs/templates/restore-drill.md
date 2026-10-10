# Restore drill — {{environment}}, {{date}}

Status: {{status}}
Script: `dev/drills/restore.sh` at commit {{commit}}. Run by: {{operator}}. Brief: §24.3, §24.4 (restore drills: quarterly in staging and after major upgrades; record measured RPO and RTO).

The dataset is synthetic. The script writes this file from its measurements, so fill nothing in by hand; `TL_DRILL_ENV` and `TL_DRILL_OPERATOR` name the environment and the person.

## What was exercised
| Path | What it proves | Result |
|---|---|---|
| Ledger archive into SQLite | The signed archive alone rebuilds a SQLite ledger and its `cur_*` tables | {{archive_sqlite_status}} |
| Ledger archive into Postgres | The same archive rebuilds a Postgres ledger (scratch database `{{pg_scratch_database}}`) | {{archive_postgres_status}} |
| SQLite online snapshot | `tl backup sqlite` output is a usable ledger | {{snapshot_status}} |
| Litestream replica | A continuously replicated copy restores after the file is lost | {{litestream_status}} |
| pgBackRest full backup plus WAL | A scratch Postgres cluster survives loss of its data directory | {{pgbackrest_status}} |

A path that was skipped says why under Findings. The shared cluster and its `tl_test` database are never used.

## Dataset
| Item | Value |
|---|---|
| Events when the archive was sealed and the snapshot taken | {{head_at_backup}} |
| Events written after that, before the loss | {{tail_events}} |
| Newest event when the loss was simulated | seq {{head_at_loss}}, recorded {{at_loss}} |
| Ledger archive | {{archive_segments}} segments, up to seq {{archive_last_seq}} |
| Schema packages | `TL_SCHEMA_DIR={{schema_dir}}` |

## Measured RPO and RTO
- **RPO events**: events committed after the newest event the recovered database holds, when the loss happened.
- **RPO seconds**: the recorded time of the newest lost event minus that of the newest recovered event, the length of history lost.
- **RTO seconds**: from the start of the restore until the restored database passed `tl ledger verify` and accepted a new event.
- A continuous path (Litestream, WAL archiving) is measured with the loss right after the last write (about one command's delay), so its RPO is close to the worst case, not the best.
- Every timing includes the start-up of the `tl` and helper commands (a second or two each); it is a floor for an operator typing the same commands.

| Path | RPO events | RPO seconds | RTO seconds | Brief target | Met |
|---|---|---|---|---|---|
| Ledger archive into SQLite | {{archive_sqlite_rpo_events}} | {{archive_sqlite_rpo_seconds}} | {{archive_sqlite_rto_seconds}} | archive RPO <= 15 min, RTO <= 1 h | {{archive_sqlite_met}} |
| Ledger archive into Postgres | {{archive_postgres_rpo_events}} | {{archive_postgres_rpo_seconds}} | {{archive_postgres_rto_seconds}} | archive RPO <= 15 min, RTO <= 1 h | {{archive_postgres_met}} |
| SQLite online snapshot | {{snapshot_rpo_events}} | {{snapshot_rpo_seconds}} | {{snapshot_rto_seconds}} | database RPO <= 5 min, RTO <= 1 h | {{snapshot_met}} |
| Litestream replica | {{litestream_rpo_events}} | {{litestream_rpo_seconds}} | {{litestream_rto_seconds}} | database RPO <= 5 min, RTO <= 1 h | {{litestream_met}} |
| pgBackRest | {{pgbackrest_rpo_events}} | {{pgbackrest_rpo_seconds}} | {{pgbackrest_rto_seconds}} | database RPO <= 5 min, RTO <= 1 h | {{pgbackrest_met}} |

The drill dataset is small, so RTO here is a floor: restore time grows with the number of events (the archive path replays every event) and with database size (pgBackRest). Compare the
trend between drills, not one number with a target. pgBackRest `archive_timeout` was {{pgbackrest_archive_timeout_seconds}} s, which bounds the unswitched WAL it can lose; the full backup took
{{pgbackrest_backup_seconds}} s and the restore command {{pgbackrest_restore_seconds}} s.

## Verification
| Check | Result |
|---|---|
| `tl archive verify` on the archive, with the public key | {{check_archive_verify}} |
| `tl archive verify --deep --db` on each restored database (every field equal to the archive) | {{check_deep_verify}} |
| `tl ledger verify` on each restored database (hashes recomputed, chains intact) | {{check_ledger_verify}} |
| Restored `cur_*` tables and events equal the original at the backup point (digest `{{digest_original}}`) | {{check_digest}} |
| A new event is accepted by each restored database | {{check_probe}} |
| A tampered copy of the archive is refused with the first divergence | {{check_tamper}} |

## Timeline
| Step | Seconds |
|---|---|
| Populate, seal, snapshot | {{t_prepare}} |
| Restore from archive into SQLite | {{t_archive_sqlite}} |
| Restore from archive into Postgres | {{t_archive_postgres}} |
| Restore from snapshot | {{t_snapshot}} |
| Restore from Litestream | {{t_litestream}} |
| pgBackRest (whole drill, including cluster create and drop) | {{t_pgbackrest}} |

## Findings
{{findings}}

## Follow-ups
- Production key custody, retention classes and object lock are human decisions (brief 24.3) and are not exercised by this drill.
- Record the date and the commit of the next drill: quarterly in staging, and after every major upgrade.
