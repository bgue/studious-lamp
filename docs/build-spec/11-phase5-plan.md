# Build spec 11 — Phase 5 plan: Expansion

Brief: §16 Phase 5, §13, §22.9. Six increments at outline level; the orchestrator expands each into tickets when the
phase starts, after the Phase 4 retro. IDs `P5-I<n>-T<nn>`.

**Human gates:** cost system connector credentials (Q1); P6 EPPM write-back (owner approval); app store distribution and the native shell (Increment 5);
licence review for any new viewer or chart dependency.

## Increment 1 — Cost display and commenting module

Cost code tree with the measure matrix (hours/qty/$ × budget/actual/earned/FTC/EAC), period selector, variance
highlighting, drill-through to contributing records, comments per code/period. Supervisor builds the matrix
projection and variance rules; implementers build screens, reports, and comment records. Later: forecast editing
pushed back by connector (separate increment when Q1 is answered).

## Increment 2 — Schedule statusing and export to P6

**Changed 2026-11-01 (owner):** the schedule display and commenting module (activity list, text Gantt, readiness
overlay, comments) moved to Phase 2 wave 4 (`specs/phase2-wave-plan.md`, P2-SCHED). What stays here: progress
statusing entry and the statusing export back to P6 (XER/XML), next to the P6 connector of Increment 3, behind its
write-back gate. Supervisor builds the statusing export; implementers build the entry screen and reports.

## Increment 3 — P6 XML import and EPPM API connector

Both produce the same `ScheduleSnapshot` structure as XER. Connector framework hardening: idempotent sync by
`external_ids`, scheduled jobs, failure handling in the integration registry. Read first; write-back behind a human gate.

## Increment 4 — Lakehouse: cross-project benchmarking and sharing

Company catalog with cross-project marts (weld rates, NDE reject rates, RFI turnaround, punch closure); per-project
DuckLake export for clients and partners; masking of personal data; restricted catalog for confidential classes.

## Increment 5 — Mobile: the full app on phones and tablets, fully distributed, with photo, video and point-cloud capture

**Roadmap item added by the owner, 2026-10-31.** Replaces the earlier "mobile and desktop PWAs, first field flows" scope.
Status: **proposed** (no spec yet); the orchestrator expands it into a fanout after the Phase 3 replica protocol (P3-I5)
is on the trunk. Labels as in `module-designs/deployment-and-merge.md`: built, designed, proposed.

**Objective.** Every screen of the product on a phone and a tablet, not only field flows: the logs, the record screen
with every tab, the forms, approvals, the feed and threads, documents with full PDF preview, model slices. Phones are
tabbed (one log or record per tab, as the terminal's screens); tablets show the list and the record side by side, as
the wide terminal layout. One-handed primary actions, 44 px targets, outdoor and glove modes (brief §22.9).

**Fully distributed.** Each phone or tablet is a full replica (`device` node kind): it holds the ledger of the
projects its owner may read (confidentiality filtered, `restricted` and `privileged` never replicate), works offline
for as long as `sync.max_offline_days` allows, and merges on sync. Sync runs device to site server to central, and
**device to device on a local network when neither is reachable (proposed)**, so a crew can share captures on a site
with no connection. What stays with the authority of the scope: gap-free numbers (provisional keys until merge),
signatures and sign-offs (valid only over the merged hash), and the online-only commands of the offline table.

**Capture on the phone.**
| Capture | How | Stored as | Linked to |
|---|---|---|---|
| Photo | camera, gallery, document scan; location and direction when allowed | file, content-addressed; thumbnail | any record (deficiency, inspection, RFI, daily log, tag) via file slots and `capture_hint: camera` |
| Video | camera, with pause and resume; chunked, resumable background upload (brief file pipeline) | file; a preview rendition and a poster frame made on the server | same, with a time mark per note |
| Point cloud | the depth sensor (LiDAR on recent iPhone Pro and iPad Pro; ARCore depth on Android) or photogrammetry from a photo set; on-device decimation for a preview | E57 or LAS/LAZ original; a tiled, streamable rendition (COPC) for viewing; georeferenced to the project or model coordinates when control points exist | a location, tag, line, model object (M12), deficiency, or as-built check; compared against the model slice (proposed) |

Captures are records first: a capture made offline is a `full`-offline record whose files upload later, so a phone
with no signal never blocks work. Large files never sit in the ledger; only their hash and metadata do.

**Proposed build.** WS-A replica core in TypeScript (IndexedDB or SQLite-in-the-browser ledger implementing the
P3-I5 protocol; same command contracts); WS-B the full screen set from the generated forms and the log standard,
phone and tablet layouts, Web Push; WS-C capture: photo and video in the PWA, point clouds through a thin native
shell (the browser has no access to the depth sensor) plus server jobs for previews, tiling and georeferencing;
WS-D device-to-device sync and its conflict tests. Playwright device tests; real-device runs on a small device matrix.

**Owner decisions needed.**
1. Native shell: the brief lists native mobile apps as out of scope (§2); point-cloud capture and reliable background
   upload need a thin native wrapper around the web app (iOS and Android). Proposed: allow the wrapper, no
   separate native UI.
2. Device-to-device sync without a site server: in scope for this increment, or later.
3. Licences: video previews need a transcoder and point-cloud tiling a library; copyleft ones (for example some
   ffmpeg builds) are a stop condition and need the owner (licence gate).
4. Device matrix, storage budget per device, and how long a phone may stay offline (with P3-Q14 encryption at rest).
5. Store distribution (already a Phase 5 human gate).

## Increment 6 — Full desktop web client, connector hardening, broadened MCP write tools

Web client over the same generated forms and command/query contracts as the TUI; connectors for ERP, client DMS,
engineering databases; MCP write tools widened per project policy with propose-by-default retained; Phase 5 exit and
v1 release checklist (§24.2 compatibility matrix, upgrade rehearsal, restore drill).
