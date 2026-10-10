# Runbooks

Operational procedures, one file per alert or recovery path (§24.6). Template: `docs/templates/runbook.md`.

- `api-and-mcp-dev.md` — run the REST API, the SSE stream and the MCP server on the dev ledger.
- `simulator.md` — run, seed, inject into and check a simulated project (`tl sim`, `just seed`).
- `rebuild-projections.md` — rebuild the `cur_*` tables from the ledger.
- `schema-package-change.md` — change a company or project pset package.
- `tui-dev.md` — run the TUI on the dev ledger.
- `workflow-link-numbering-config.md` — change a workflow, an expected link or a numbering pattern.
- `webhook-operations.md` — dead-letter queue, replay, secret rotation, disabled subscriptions (P0-I5).
