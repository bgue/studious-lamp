# P0-I8-T50 — Docs: modules the audit found undocumented (tl-api, tl-lake, tl-sim, tl-cli)

Status: ready
Tier: haiku
Labels: docs
Depends on: P0-I8-S43 (merged into the base of this branch)
Branch: `p0/i8c-t50-docs-undocumented-modules`

## Goal
Every top-level module of `tl_api`, `tl_lake`, `tl_sim` and `tl_cli` is named in its package README. The audit tool `dev/tools/audit_docs.py` lists the ones that are not; after this ticket it lists none for these four packages, except `tl_cli.scaffold` and `tl new`, which the supervisor documents later.

## Brief references (pasted)
> **Docs rules (skill `throughline-docs` section 2):** lead with what the reader needs to act; one idea per sentence; tables for parallel facts; no model names anywhere; keep each package README under about 150 lines; do not duplicate, link to the single source. **Package README (`docs/templates/package-readme.md`):** a *Public interface* table with columns `Symbol | Kind | Purpose`.

### The rows to add (one per module; wording from each module's own docstring)
`packages/tl-api/README.md`, *Public interface* table:
```
| `tl_api.context.ApiContext` | class | The per-application context route handlers read from `request.app.state` |
| `tl_api.main` | module | The server entry point: `uv run python -m tl_api` (or `just serve`) |
| `tl_api.models` | module | Response and request models that have no `tl_core` class of their own |
```
`packages/tl-lake/README.md`, *Public interface* table:
```
| `tl_lake.errors` | module | The errors `tl_lake` raises; every one is a `LakeError`, so a caller can catch the family |
| `tl_lake.ingest` | module | Bulk loading into the lake through NDJSON files (never `executemany`; L-P0-I7-B1) |
```
`packages/tl-sim/README.md`, *Public interface* table:
```
| `tl_sim.assertions` | module | `sim_assert`: compare what the scenario intended with what the suite holds |
| `tl_sim.cli` | module | The `tl sim` group: the five operations plus `run` and `seed` |
| `tl_sim.connector.HttpConnector` | class | The orchestrator's door to a running suite: the API over HTTP, MCP for proposals |
| `tl_sim.groundtruth` | module | The ground-truth log: what the scenario intended, one JSON line per `GroundTruth` |
| `tl_sim.injections` | module | Injected events: one-off steps played by an actor after the day's regular actors |
| `tl_sim.orchestrator_names` | module | The fixed identities of the simulator (a leaf module that actors and the orchestrator share) |
| `tl_sim.reader.SimReader` | class | What `sim_assert` reads from the suite, and its HTTP implementation |
```
`packages/tl-cli/README.md`, *Public interface* table (put them before the last row, `tl_cli.main:app`):
```
| `tl_cli.file_reconcile` | module | `tl file reconcile`: compare the ledger's file rows with the object store |
| `tl_cli.webhook_common` | module | Helpers shared by the `tl webhook` commands: the unit-of-work factory, scope and error output |
| `tl_cli.webhook_ops` | module | The second half of `tl webhook`: `dlq ls`, `dlq redrive`, `disable`, `enable`, `rotate-secret` |
```

## Interfaces (verbatim from repo at the branch point)
None (documentation only).

## Context (read these, nothing else)
- `packages/tl-api/README.md`
- `packages/tl-lake/README.md`
- `packages/tl-sim/README.md`
- `packages/tl-cli/README.md`
- `dev/tools/audit_docs.py` (only to run it)
may explore: (none)

## Allowed paths
- `packages/tl-api/README.md`
- `packages/tl-lake/README.md`
- `packages/tl-sim/README.md`
- `packages/tl-cli/README.md`

## Steps
1. Insert each block of rows at the end of the *Public interface* table of its README (a table ends at the first blank line), keeping the three-column format. Do not reword the rows and do not touch any other line.
2. Run the audit tool for the four packages and paste its output.

## Acceptance
```
uv run python dev/tools/audit_docs.py --package tl-api --package tl-lake --package tl-sim --package tl-cli
just check
```
Expected: `tl-api: 0 finding(s)`, `tl-lake: 0 finding(s)`, `tl-sim: 0 finding(s)`, and for `tl-cli` exactly two findings (`undocumented: module tl_cli.scaffold` and ``undocumented: command `tl new` ``). No README grows past 150 lines.

## Tests to add
None (documentation only).

## Report requirements
Standard report. Paste the audit output before and after.

## Escalation triggers
- Stop and report *Blocked* if a README has no *Public interface* table, or a row's claim is contradicted by the README's own text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
