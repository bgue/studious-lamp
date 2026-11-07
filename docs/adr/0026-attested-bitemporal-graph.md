# ADR-0026 — An attested, bitemporal knowledge graph as a read model over the ledger

Status: proposed (2026-11-07, design only; the hash-chain change in section 6 is a separate core decision)
Date: 2026-11-07
Deciders: repository owner; orchestrator (acceptance). Touches confidentiality, so a human gate (§25.5).
Brief sections: §5.1, §5.2 (bitemporal queries), §9 M10 (evidence trail), §18.11 (external parties), §8
Builds on: ADR-0016 (viewer), `module-designs/deployment-and-merge.md`, `module-designs/external-parties.md`.
Proposed neighbours: ADR-0024 (constraints) and ADR-0025 (intents), both plan-checked on branch `p2/i2`; section 3
follows them.
Spec: `docs/build-spec/specs/graph-views.md`. Nothing here is built.

## Findings (checked against the code on trunk)
**a. Valid time is a field on every event but real world-time is not.**
- The envelope has `effective_at` on every event ("business time", `schema/core/ledger.yaml:67-70`; brief `§5.1:232`;
  `ledger/types.py:30,53`; `sqlite/schema.sql:13`). In a real project it is always `recorded_at`:
  `sqlite/ledger.py:155-157` and `postgres/ledger.py:171-173` default it to the moment recorded; only simulation scopes may
  set it (`tl_api/effective.py:5-6,23-33`); proposals stamp `now` (`services/proposals.py:487,560,623`).
- The world date lives in payload fields, named per module (`_on`, `_date`, `_at`, `period`, `effective_from/to`). Payload
  classes with a world-time field, of the total (`schema/**/events*.yaml`, counted 2026-11-07):

| Module | With field / total | Fields (file:line) | Gap |
|---|---|---|---|
| core | 5 / 69 | `expires_at` 512, 572, 808, 1205; `produced_at` 1447 | All operational. None on `Record.*`, `Link.*`, `Pset.ValuesSet`, `Workflow.Transitioned` (43-145, 148-275, 281) |
| documents | 9 / 15 | `revision_date` 138, `issued_on` 158, 286, `due_date` 262, 331, `responded_on` 306, 360, `closed_on` 378 | Derivation and job events: leases and retries only |
| correspondence | 15 / 36 | `sent_on` 68, `received_on` 70, `issued_on` 195, `responded_on` 234, clock `start_on`/`due_on` 385-461 | Best covered; `date_reason` (195, 739, 865) is a per-event back-dating note, not a shared rule |
| engineering | 4 / 10 | `effective_from`/`effective_to` 51-53, 109-111, 75, 136 | The only true validity intervals; none on tags |
| materials | 7 / 19 | `promised_date` 200, `received_on` 238, `inspected_on` 291, `decided_on` 309 | `StockLot.Moved` (movements, ADR-0022) has no date |
| schedule | 2 / 12 | `data_date` 59, 208 | The data date is of the plan, not of the event |
| cost | 2 / 4 | `period` 75, 101 | Period text, not an interval |
| awp | 2 / 19 | `forecast_date`/`actual_date` 345-388 (EWP, PWP refs) | CWP, IWP, path and release events carry none |
| schemareg | 1 / 12 | `expires` 241 (waiver) | Adoption has no effective date |
| legacy | 0 / 10 | none | Import runs carry no source-world date |
Dates are ISO days, not instants, and no event has an interval except engineering. About 218 payload classes exist.

**b. A per-scope hash chain exists today; there is no content hash.**
- `hashing.py:28-46`: SHA-256 over previous hash, event id, stream id, stream version, event type, canonical payload and
  `recorded_at`. Stored in `prev_hash` and `hash` (`sqlite/schema.sql:17-18`, `postgres/ddl.py:33-34`). The append reads the
  scope's newest hash (`sqlite/ledger.py:143-146`, `postgres/ledger.py:159-162`, index `ix_events_scope_seq`).
- **Not covered by the hash:** `effective_at`, `actor`, `source`, `scope`, `schema_version`, `stream_type`, `correlation_id`,
  `causation_id`. A tamperer can change who did it or the valid time and the chain still verifies (`archive/segments.py:114-124`).
- Verification: `archive/verifier.py:85-100,216-280`. Signing: Ed25519 over each sealed segment's manifest
  (`archive/types.py:33-47`), not per event. The lake checks the event at its watermark (`tl_lake/sync.py:360-365`).
- Other hashes: file `sha256` (`correspondence/events.yaml:203`, content-addressed files), `effective_schema_hash` on
  `Pset.ValuesSet` (`core/events.yaml:135`) and `Workflow.Transitioned` (314). `facts_hash` does not exist.
- **Cost of the chain, per scope versus global.** SQLite takes one writer at a time (`sqlite/engine.py:63-70`, `BEGIN IMMEDIATE`);
  Postgres takes one advisory lock in every write (`postgres/engine.py:36-41,198-200`). Writers are already serialised
  globally, so a global head adds no contention. A global head reads by primary key and needs no index; the per-scope read
  uses an index that stays for `read_after`. Size is the same: two 64-character columns per event either way.
  The difference is Phase 3: a replica pulls only what its owner may read, which leaves gaps in a scope chain
  (`deployment-and-merge.md:50-51`, R-P3-3) and would leave gaps at almost every event in a global one. Replicas keep a local chain of
  pending commands and the authority assigns the canonical `seq` and chain at merge (`:39`).

**c. Mapping.** Section 3. **d. Phase 3 views.** The viewer gains `party` (P3-I8 T01, `09-phase3-plan.md:273-280`): records
assigned to or shared with the party plus one `belongs_to` hop, never `restricted` or `privileged`
(`external-parties.md:34-41,59-62`); lake rows for hidden streams stay as bare `seq` rows (`tl_lake/sync.py:113-120`). The
GC is the internal viewer; the client and subcontractors are external parties. Existing "as of" (`correspondence/evidence.py:12,74`)
replays by `recorded_at` only: it answers "as known", never "as it stood".

## Definitions
- **Bitemporal**: each fact has a transaction time (when the ledger learned it: `recorded_at`, and when a later event
  superseded it) and a valid time (when it was true in the world: from, to, either may be unknown).
- **Attestation**: every fact links back to the event or events it came from, and so to who recorded it and when.
- **Hash chain**: each event's hash includes the previous one, proving order and making edits detectable.
  **Signing** is optional: designed for, not required.
- **Party scope**: one graph per party and per viewer clearance, built by the one viewer seam; never one global graph.
  A hidden node, edge or fact looks exactly like a missing one: no stub, no count, no gap.

## Decision
### 1. Data model
- **Node**: any record (`cur_core_record`), plus parties, actors (`user:`, `svc:`, `agent:`) and files by id. No new node store.
- **Edge**: a link (`cur_links`) and any typed reference a payload names (`to_ref` and the `*_id` fields).
- **Fact**: one row of a generated table `cur_facts`: subject, predicate (field or relation), object (value or node),
  `valid_from`, `valid_to` (nullable; unknown stays unknown, never guessed), `recorded_from`, `recorded_to`,
  `event_id`, `seq`, `actor`, `corrects` (a fact id) and `derived_from` (event ids, for computed facts).
- Valid time comes from payload fields tagged `tl:valid_time` in the schema (data, section 5); an untagged fact has valid
  time unknown and says so. Envelope `effective_at` is never read as world time.

### 2. Verifying a fact back to the ledger
Open `event_id`, recompute its hash with `recomputed_hash`, follow `prev_hash` to the scope's checkpoint, compare that with
the signed segment manifest if the event is sealed. Four outcomes: verified, verified but not yet sealed, divergent, and
"cannot check" (the viewer may not read the neighbours). A replica checks per-event hashes only (R-P3-3). A derived fact
verifies every event in `derived_from`. Until the separate chain decision (section 6) lands, verification states that
`actor`, `source` and valid time are not covered.

### 3. How things map
| Thing | Node, edge or fact | Provenance |
|---|---|---|
| Record (`Record.Created/Updated`, `Pset.ValuesSet`) | Node; one fact per changed field or property | The event; `effective_schema_hash` is a fact on the property naming the schema in force |
| `Record.Corrected`, `Record.Voided`, `Link.Retracted` | New fact with `corrects`; the old fact gets `recorded_to`; voided node stays | The correcting event and its mandatory reason |
| Link (`Link.Added/Suggested/Accepted/Verified/Flagged`) | Edge with status; `source` and `confidence` as facts | Link events; `verified_by` is a fact; a suggestion is an edge with status `suggested` |
| Actor | Node; `recorded_by` edge from every fact | `actor` plus `on_behalf_of` in the payload |
| Proposal (`Proposal.Created/Accepted/Rejected`) | Node; the resulting facts carry `causation_id` to it | Created by (agent or rule), accepted by (person); a rejected proposal changes no fact |
| Workflow transition | Fact `state` with valid from the transition; guards in provenance | `Workflow.Transitioned`, including `signature` when present |
| Constraint, ADR-0024 (proposed) | Node on a record with valid-time fields; edge `constrains` to each target; facts `open`/`cleared` | Create and clear events and the person who cleared it |
| Intent, ADR-0025 (proposed) | Fact on the event: why, next, toward, goal_ref; edge `toward` to the end state | A nullable `intent` column added as an optional last part of the event hash, only when present, so it is covered by the chain and old events hash as before |
| `APPROVALS.md` entries | Not graph data: a file of delegated build approvals, not ledger events | Approvals that matter are `Proposal.Accepted` and signed transitions |

### 4. Corrections, retractions, two clocks
Nothing is deleted. A correction closes the old fact's transaction time and opens a new row; valid time changes only
when the correcting event says so. "As known on D" = `recorded_from <= D < recorded_to`. "As it stood on D" = valid
interval contains D, using the latest known version. The two together answer "what did we believe on D1 about D2".

### 5. Scoping
The graph is a function of the viewer: nodes pass `hidden_sql` first, then an edge or fact survives only if both ends and
its own source events are readable. No "hidden" count, no `seq` or hash of a hidden neighbour. A derived fact depending on a
hidden event is dropped for that viewer, not shown with a gap (open question 2). A party graph is computed through
`Viewer.party`; a stored per-(party, clearance) copy is only a cache that a rebuild can recreate.

### 6. Where it lives
**Recommend: a projection**, generated DDL (`cur_facts`, rule 4 of `AGENTS.md`), in the operational database. Reasons:
the confidentiality seam already works there; replicas rebuild projections from the merged ledger, so every node agrees
(`deployment-and-merge.md:20-21`); the lake runs on the authority only (`:60`) and is queryable by every user. A lake mart
is a later analytic copy for whole-project path queries; an export (GraphML, RDF) is a viewer-filtered file made from
the projection. Projection rebuild cost grows with the ledger; fact rows are bounded by changed fields, so measure on the
scale fixture before Phase 3 sync.

### 7. The chain is its own core decision (name: "Ledger hash v2, an attestation chain")
Not decided here. Changing an existing event is a stop condition (`AGENTS.md` rule 3), so history cannot be re-hashed or
back-filled with an UPDATE (the triggers refuse it). **Recommendation:** keep the per-scope chain as is; add a second
chain, hash v2, over all envelope fields plus the v1 hash, stored in a side table keyed by `seq`, written in the append
transaction for new events and built by a one-off job over the existing order for old ones, ending in a signed
genesis checkpoint. Do not add a global chain. Optional per-event signatures use hash v2 and are off by default.

## Cheap now, expensive later
1. **Reserving a hash column is not the saving.** A nullable column is a metadata change on both databases, and old rows could
   never be filled (no UPDATE). What is dear to change later is the shape of what crosses boundaries: the archive segment
   columns (`segments.py:37`) and manifest, the lake bronze table, and the Phase 3 mirror and handshake. **Reserve now:** a
   `hash_version` (1 today) in the manifest and the sync handshake. Cost now: S, a few lines each. Later: a format
   migration across every sealed archive and every replica.
2. **Tag world-time fields (`tl:valid_time`)** in the schema before Phase 3 modules add events. Now: a rule plus a pass over
   the ~218 classes (about 8 H tickets, data only). Later: the same pass plus upcasting what was recorded without it.
3. **Decide hash v2 coverage before the first replica ships.** Later cost: every mirror holds v1 hashes forever and every
   verifier dual-checks.
4. **Intent in the hash:** settled by ADR-0025 (a column plus an optional last hash part, present only when an intent exists, so existing hashes do not change). Nothing more to reserve.
5. **Make graph reads functions of the viewer from the first query.** Later: a retrofit across routes and a second security gate.
6. **Rename nothing yet but note the clash:** link payload `source` (manual, rule, ai, import) shares a name with envelope `source`.

## Phasing (all build deferred; `DEFERRED.md:50`)
Phase 2 (now, tiny): items 1, 2, 4 above and the open questions. Phase 3 with replicas: hash v2 decision and build,
`cur_facts` projector, party and clearance walking tests (seven readers). Phase 4: graph views (`graph-views.md`).

## Open questions for the owner
1. Is a signed genesis over history acceptable, with hash v2 trusted only from that point? 2. Show or drop a derived
fact whose input is hidden? 3. Should back-dating a real project (envelope `effective_at`) ever be allowed? Proposed: no.

## Plan check (2026-11-07) and answers
`4 PLANCHK docs/adr/0026 + specs/graph-views.md`, planner tier, one pass. All twelve findings accepted by the
orchestrator; where an answer differs from the text above, the answer wins.
- F1 HI: ADR-0024 copied `cleared_at` into the envelope `effective_at`, and deployment-and-merge.md:58 sets it to device time. **Accepted:** the envelope `effective_at` is capture time only (`recorded_at` online, device time offline), never world time. The ADR-0024 copy is dropped before its commands piece is built (decision sent to P2-I2 round 3); world dates stay in payload fields and projection rows.
- F2 HI: sealed events are already covered whole: the signed manifest holds `ndjson_sha256` over complete event lines (`archive/segments.py:210`), actor, source and `effective_at` included. **Accepted:** Finding b is corrected to "the open gap is unsealed events and database rows edited after sealing"; verification (section 2) compares the full database row with the sealed line; hash v2 only closes the unsealed window.
- F3 HI: 64 of 69 core classes, all links and `Workflow.Transitioned` carry no world date, so "unknown, never guessed" would leave the as-stood view nearly empty. **Accepted:** fallback `valid_from = recorded_at`, labelled `as recorded`; `date not recorded` only when a tagged field is null.
- F4 MD: deadlines and plans (`due_date`, `promised_date`, `forecast_date`, `expires_at`, `data_date`) are values, not valid time. **Accepted:** `tl:valid_time` takes `at`, `from` or `to` and marks only when-it-happened fields; about 47 classes have one, not 218.
- F5 MD: an annotation applies to old events without upcasting, and tagging touches `schema/**`. **Accepted:** the stub now is the annotation declared in `annotations.yaml`, one rule in the module standard and 1 Haiku lint ticket so wave 3 events carry the tag (lands with the ADR-0025 slice, before wave 3; orchestrator approval with an APPROVALS line). Back-tagging the ~47 classes moves to the Phase 3 projector (1 H more).
- F6 MD: the manifest already has `format: "tl-archive/1"`, and no sync handshake exists. **Accepted:** the `hash_version` stub is dropped; v2 ships as `tl-archive/2`; the handshake version belongs in the Phase 3 sync ADR.
- F7 MD: **Accepted:** hash v2 is per scope. A signed genesis row commits to each scope's v1 head, v2 covers new events only, mirrors carry each event's v2 hash, and the side table gets append-only triggers.
- F8 HI: "Cannot be checked from here" would reveal a hidden event in the scope chain. **Accepted:** the server verifies under the system view and returns only the verdict word; "cannot check" is for replicas only.
- F9 MD: **Accepted:** the open-constraints column counts visible rows only and is in the twin test; subtree questions filter at every hop; shared saved views are deferred.
- F10 MD: **Accepted:** views effort is 2 S (reader with provenance; routes with walking and twin tests) plus about 10 H (screens over a merged `ClientInterface.graph`).
- F11 MD: **Accepted:** v1 is the record tab, `GraphLog`, the modal and the web drawer; the slider, node-link picture and following pane come after the web increment; project start gets a key other than `Home`.
- F12 MD: **Accepted:** approvers are the owner for hash v2 and the orchestrator for scoping (ADR-0008 d6), each with an APPROVALS line. Sec rows: graph filter, verdict, party scope, v2 append, each with its commit range. Route walks use the six real readers, not "system".
