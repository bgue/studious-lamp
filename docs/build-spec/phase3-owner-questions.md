# Phase 3 — questions only the owner can answer

Status: open, 2026-10-20. Same style as the Phase 2 questions. The answers become an ADR recorded before wave 0 of
`09-phase3-plan.md`. Each question gives the options, a recommended default, and what waits on it.

| # | Question | Blocks |
|---|---|---|
| P3-Q1 | Replica scope for v1: laptop replica only, or site node too | I5 T08; wave 3 sizing |
| P3-Q2 | Clock arithmetic shared with the Issue engine: import or move | I1 T03 |
| P3-Q3 | Models as documents: document type, or a Document subclass | I6 T01; wave 0 ADR |
| P3-Q4 | External parties: accounts with a party scope, guest links only, or both | I8 T01–T03; I7 T09; wave 0 ADR |
| P3-Q5 | Who signs test certificates, and what re-authentication means | I4 T05 |
| P3-Q6 | Calibration and continuity blocks: hard or soft by default | I2 T02a, I3 T03 |
| P3-Q7 | NDE contractor: inbound endpoint only, or an external account too | I3 T08; I8 T07 |
| P3-Q8 | Offline numbering: provisional keys or reserved ranges | I5 T05 |
| P3-Q9 | Web toolchain and licences: Node, Playwright, xeokit (AGPL), IfcOpenShell (LGPL) | I6 T02, T07; I7 T01; wave 0 |
| P3-Q10 | Legal domain: approver, and whether cleared people may replicate or export Legal items | I8 T05 |
| P3-Q11 | Delegation of the Phase 3 human gates | wave 0; every gate |
| P3-Q12 | Welder qualifications and WPS: fixture data or a loader from the GC's register | I3 T01 |
| P3-Q13 | TUI model snapshots (headless Chromium): build or defer | I7 T08 |
| P3-Q14 | Replica encryption at rest: database-level or operating-system level | I5 T07 |

---

## P3-Q1 — Replica scope for v1

Brief §22.1 names two replicas: a laptop running embedded Throughline, and a site node serving TUIs on the LAN with
multi-level sync. The embedded server already exists (`tl serve` over SQLite, remote TUIs). A site node adds a
second hop in the protocol (a replica that is also an upstream).

| Option | What it means |
|---|---|
| A. Laptop replica only | One hop; the site node is Phase 5 with the PWAs |
| B. Both, site node last | A plus multi-level sync as the final I5 ticket, droppable if wave 3 runs long |
| C. Site node first | The laptop syncs to the node, the node to central; two hops from the start |

**Recommended default: B.** The protocol is written so a replica can be an upstream (cursors per peer); the second
hop is built only if time remains.

## P3-Q2 — Clock arithmetic shared with the Issue engine

`tl_mod_correspondence.clocks` is pure (replay of facts with a project calendar). The Issue engine needs the same due
dates, pauses and warnings. Importing it is the second module-to-module import (P2 T-7 allowed two).

| Option | What it means |
|---|---|
| A. `quality` imports `tl_mod_correspondence.clocks` | No refactor; the third consumer (Phase 4 ITRs) triggers the move |
| B. Move the pure functions to `tl_core/clocks.py` now | A small refactor of P1-I5 code with its tests, one ticket, before I1 |

**Recommended default: B**, done at wave 0 by the orchestrator's supervisor as the first Phase 3 ticket, because the
move is mechanical today and costly once two modules depend on the module path.

## P3-Q3 — Models as documents

Brief §23: `ModelDocument is_a Document`, `ModelRevision is_a Revision`. On the ADR-0010 seam a class is one typed
table owned by one module; a cross-module `is_a` does not exist.

| Option | What it means |
|---|---|
| A. A `documents.Document` of document type `model`; the IFC is the revision file; `models.ModelRevision` is a module record `derived from` the revision | All of M1 (revisions, transmittals, pins, stale rule, feed) applies with no change; model-specific fields live on the `models` record |
| B. Subclasses inside the `documents` module | The documents module grows model fields and the ingest dependency |
| C. A `models` module with its own `ModelDocument` record and no M1 behaviour | Loses revision control, pins and transmittals |

**Recommended default: A.**

## P3-Q4 — External parties

Brief §18.11 lists external-party accounts (ABAC by party), guest links, feed and thread participation, and a portal
page. ADR-0013 has three roles; no per-record access exists.

| Option | What it means |
|---|---|
| A. Guest links only in Phase 3 | No new role; sign-off, RFI response, MTR upload and acknowledgement by link; no portal |
| B. Accounts with role `external` and a party scope on the viewer, plus guest links | One ADR, one security gate, a sixth walking reader; the portal page becomes possible |
| C. B plus feed and thread participation for external accounts | B plus the feed and thread visibility rules (the thread follows the record already) |

**Recommended default: B**, with C's thread participation included because ADR-0018 derives thread visibility from
the record. Feed posting by external accounts waits.

## P3-Q5 — Who signs test certificates; re-authentication

The brief: "signed via e-signature". Phase 1 has no re-authentication over the API. P2-Q2 may add a
`workface_planner` role.

| Option | What it means |
|---|---|
| A. `controller` signs; re-authentication is a session-age check (`auth.reauth_window_minutes`) | No auth change; the limit is recorded |
| B. A `qc_lead` role signs | A gated role change (ADR-0013 mechanism) |
| C. A, plus the P2-Q2 role may sign | Two roles may sign; the setting `testing.certificate.signers` counts distinct signers |

**Recommended default: C** if P2-Q2 chose B, else A. Password re-entry over the API is a Phase 5 item.

## P3-Q6 — Calibration and continuity blocks

| Option | What it means |
|---|---|
| A. Hard everywhere | A past-due instrument or a lapsed welder refuses the entry |
| B. Soft everywhere | Entry allowed; a constraint with source `check` and a warning |
| C. Hard for pressure tests and NDE, soft for inspections and welds | The setting `quality.calibration.block_mode` per command group |

**Recommended default: C.** Offline entries that fail only a soft guard at merge become conflicts a person can waive.

## P3-Q7 — NDE contractor access

| Option | What it means |
|---|---|
| A. Inbound endpoint `acme-nde` only (HMAC, JSONata) | The contractor's system posts; no person signs in |
| B. A plus an external account for the contractor's coordinator | Depends on P3-Q4 B; the coordinator sees their NDE requests in the portal |

**Recommended default: A** for the phase exit; B follows P3-Q4 in I8.

## P3-Q8 — Offline numbering

Brief §22.4: provisional keys (`~P123-NCR-7F3Q`) or reserved ranges per replica (`numbering.offline.mode`).
`reserve_range` was never built (Phase 2 §0).

| Option | What it means |
|---|---|
| A. Provisional keys with an alias kept after merge | One allocator path; every key lookup resolves aliases; gap-free numbering preserved |
| B. Reserved ranges per replica | Keys are final offline; gaps when a replica is revoked; `reserve_range` built and gated (numbering allocation is supervisor-tier) |
| C. Both, by setting | A now, B when a GC asks for it |

**Recommended default: A**, the setting declared with `provisional` as its only accepted value until B exists.

## P3-Q9 — Web toolchain and licences

ADR-0006 refuses GPL, LGPL and AGPL during the run; brief Q9 says xeokit (AGPL) needs a licence decision before
customer distribution; IfcOpenShell is LGPL; ifctester and xeokit-convert follow; Playwright downloads a browser.

| Option | What it means |
|---|---|
| A. No viewer in Phase 3; IfcOpenShell as an optional extra; text context only | The §16 overlay exit clause is not met |
| B. Viewer behind `ModelViewer` in `web/`, AGPL allowed for dev builds only and never distributed; IfcOpenShell as an optional extra in the envelope with a stub path; Playwright skipped where no browser exists | An owner allow-list entry for each, recorded in `APPROVALS.md`; the commercial xeokit licence decided before Phase 5 |
| C. Commercial xeokit licence now | Spend and a contract |

**Recommended default: B.** The build environment is checked at wave 0 (Node present, browser download allowed);
if not, I7 WS-A runs on the `NullViewer` and the overlay clause is demonstrated by the API colour map plus the
Playwright test on a developer machine.

## P3-Q10 — Legal domain

| Option | What it means |
|---|---|
| A. `privileged` default, feed `none`, thin webhooks, never replicated, exported, laked or read by agents, whatever the clearance | The brief's rule verbatim |
| B. A, but a cleared person may take Legal items offline | A replica holding privileged text |

**Recommended default: A.** The legal lead approves the domain file; the tests of I8 T05 prove each exclusion.

## P3-Q11 — Delegation of the Phase 3 human gates

| Option | What it means |
|---|---|
| A. As Phase 2 (P2-Q10's answer) | Schema delegated to the orchestrator; security, licence and legal in person |
| B. Also delegate the security gates | The replica and external-party ADRs would be orchestrator-approved |
| C. Stop at each increment | Eight stops |

**Recommended default: A.** Three stops: wave 0 (ADRs, licences), I5 T07 (replica security), I8 T01 and T05
(external scope, Legal).

## P3-Q12 — Welder qualifications and WPS

| Option | What it means |
|---|---|
| A. Fixture data: `co.acme.piping@1.0.0` carries WPS documents and sample qualifications | Nothing real; the GC's register loads later through the P1-I8 loader framework |
| B. A loader for the GC's welder register now | Needs the register's format |

**Recommended default: A**, with the loader mapping template written (06 cross-phase rule 2).

## P3-Q13 — TUI model snapshots

Brief §23.5 (a): a server-rendered snapshot by headless Chromium in graphics terminals. ADR-0002 constrains browser
downloads; a rendering farm is operations.

| Option | What it means |
|---|---|
| A. Defer to Phase 5 | Text context, pairing and deep links now |
| B. Build with Playwright's Chromium when present | A job `models.snapshot`, a cache per record and revision |

**Recommended default: A.**

## P3-Q14 — Replica encryption at rest

Brief §22.6: local stores encrypted at rest, revocable, remotely wipeable.

| Option | What it means |
|---|---|
| A. Operating-system encryption (documented requirement) and remote wipe by revocation plus a local purge command | No new dependency; the limit is recorded in the ADR |
| B. SQLCipher | A native build dependency with licence and packaging work |

**Recommended default: A** for Phase 3, B filed for the pilot.
