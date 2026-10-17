# Runbooks

Operational procedures, one file per alert or recovery path (§24.6). Template: `docs/templates/runbook.md`.

- `lake-sync.md` — run, check and repair the DuckLake copy; handle a refused `lake_query` or a stale lake.
- `dev-mcp.md` — run the dev MCP server for coding agents: tools, resources, what it refuses (P0-I8).
- `api-and-mcp-dev.md` — run the REST API, the SSE stream and the MCP server on the dev ledger.
- `settings.md` — about:config: read, change, lock, schedule, undo and move settings; carry out a pending effect (P0-I8).
- `proposal-review-queue.md` — review, accept or reject what AI agents proposed through MCP (P0-I6).
- `simulator.md` — run, seed, inject into and check a simulated project (`tl sim`, `just seed`).
- `rebuild-projections.md` — rebuild the `cur_*` tables from the ledger.
- `schema-package-change.md` — change a company or project pset package.
- `tui-dev.md` — run the TUI on the dev ledger.
- `workflow-link-numbering-config.md` — change a workflow, an expected link or a numbering pattern.
- `webhook-operations.md` — dead-letter queue, replay, secret rotation, disabled subscriptions (P0-I5).
- `ledger-archive-and-verify.md` — seal the ledger into signed segments, verify the archive and the database, read the first divergence (P0-I7).
- `restore-from-archive.md` — rebuild a SQLite or Postgres database from the archive alone (P0-I7).
- `pgbackrest-restore.md` — pgBackRest backup and restore for Postgres, and the scratch-cluster drill (P0-I7).
- `sqlite-backup-and-litestream.md` — SQLite snapshots and Litestream replication (P0-I7).
- `extension-types.md` — register, change and retire a company record type; repair a record whose stored body failed verification (P0-I8).
- `object-store-reconciliation.md` — compare the ledger's file hashes with the object store (P0-I4).
- `run-on-postgres.md` — run the API, the TUI and the `tl` commands on a Postgres ledger: `TL_DB` as a URL, `sslmode`, what differs from SQLite (P1-I0).
- `postgres-local-setup.md` — start Postgres, run the parity suite, clean up after a killed run (P0-I5).
- `performance-benches.md` — seed 100k records, run the §15 benches on SQLite and Postgres, read the numbers (P0-I8).
- `accounts-and-access.md` — accounts, roles, sign-in, agent tokens, the demo account, recovery from a locked-out or restored system, and the release gates for authentication (P1-I0).
- `engineering-standards-and-tags.md` — load the company standards, change a tag class, preview and apply a tag-list import, read the tag reports (P1-I1).
- `documents.md` — register, issue, re-pin stale links, transmittals, reviews, the legacy register import and recovery (P1-I2).
- `derivation-pipeline.md` — register a document schema, run the worker, read a failed job, preview and approve a publication, take it back, requeue after a restore (P1-I3).
- `schedule-snapshots.md` — upload, build, publish and compare P6 schedule snapshots, the worker, reconcile after a restore, the orphan-flagging job, and the cost snapshot import (P1-I4).
