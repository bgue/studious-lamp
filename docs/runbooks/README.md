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
- `postgres-local-setup.md` — start Postgres, run the parity suite, clean up after a killed run (P0-I5).
- `performance-benches.md` — seed 100k records, run the §15 benches on SQLite and Postgres, read the numbers (P0-I8).
