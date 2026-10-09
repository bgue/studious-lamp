# Build spec 11 — Phase 5 plan: Expansion

Brief: §16 Phase 5, §13, §22.9. Six increments at outline level; the orchestrator expands each into tickets when the
phase starts, after the Phase 4 retro. IDs `P5-I<n>-T<nn>`.

**Human gates:** cost system connector credentials (Q1); P6 EPPM write-back (owner approval); PWA store distribution;
licence review for any new viewer or chart dependency.

## Increment 1 — Cost display and commenting module

Cost code tree with the measure matrix (hours/qty/$ × budget/actual/earned/FTC/EAC), period selector, variance
highlighting, drill-through to contributing records, comments per code/period. Supervisor builds the matrix
projection and variance rules; implementers build screens, reports, and comment records. Later: forecast editing
pushed back by connector (separate increment when Q1 is answered).

## Increment 2 — Schedule display and commenting module

Activity list and text Gantt in the TUI over XER snapshot history, filtered by WBS/activity codes; AWP readiness
overlay; comments per activity; progress statusing export back to P6 (XER/XML). Supervisor builds the Gantt layout
engine and the statusing export; implementers build screens and reports.

## Increment 3 — P6 XML import and EPPM API connector

Both produce the same `ScheduleSnapshot` structure as XER. Connector framework hardening: idempotent sync by
`external_ids`, scheduled jobs, failure handling in the integration registry. Read first; write-back behind a human gate.

## Increment 4 — Lakehouse: cross-project benchmarking and sharing

Company catalog with cross-project marts (weld rates, NDE reject rates, RFI turnaround, punch closure); per-project
DuckLake export for clients and partners; masking of personal data; restricted catalog for confidential classes.

## Increment 5 — Mobile and desktop PWAs on the replica protocol (§22.9)

IndexedDB ledger implementing the Phase 3 sync protocol; first field flows (feed, lookup by key/QR, camera uploads,
inspections and checklists, punch walkdown, weld/boltup entry, toolcrib, scaffold status, IWP packs, raise RFI, slices
under 50 MB, approvals and guest links); one-handed UX rules; Web Push. Fanout: WS-A replica core (TypeScript),
WS-B flows, WS-C model slices on mobile. Playwright device tests.

## Increment 6 — Full desktop web client, connector hardening, broadened MCP write tools

Web client over the same generated forms and command/query contracts as the TUI; connectors for ERP, client DMS,
engineering databases; MCP write tools widened per project policy with propose-by-default retained; Phase 5 exit and
v1 release checklist (§24.2 compatibility matrix, upgrade rehearsal, restore drill).
