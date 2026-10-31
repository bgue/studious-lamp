# Deployment shapes and merge: central, on-premises, on-device

Status: v0.1, 2026-10-30. The owner wants one product that runs centrally on the web, on-premises on a site server,
or on a device, with the data of all three mergeable, as a property of the data model. Sources: brief §5, §22, §24;
ADR-0016, ADR-0017; `09-phase3-plan.md` I5, `phase3-contracts-draft.md` §3, `phase3-risks.md` R-P3-1 to R-P3-3.
Labels: **built** is on the trunk; **designed** is in the brief, a plan or a contract; **proposed** is new here.

## 1. The three shapes in the model's terms
| Shape | Database | Serves | Role in the merge |
|---|---|---|---|
| Central (web, SaaS or the company's data centre) | Postgres | Everyone; API, MCP, webhooks, lake | Authority: canonical `seq`, numbering, hash chain, outbox |
| Site server (on-premises edge node) | SQLite or Postgres | Site TUIs on the LAN | Replica with its own users; may be upstream of laptops |
| Device (laptop; phone and tablet in Phase 5 I5) | SQLite embedded; in-browser ledger on a phone | One owner | Replica with a scope subscription; device-to-device sync on a local network proposed (Phase 5 I5) |

The same core runs in all three (built: dialect-neutral core, SQLite and Postgres adapters with a parity suite, the
embedded TUI client over SQLite, `tl serve`). What differs is authority and what each node may hold.

## 2. What the data model gives (built) and why merging is possible
- **Events are the truth; state is a deterministic projection.** A command is validated by a service and emitted as
  events in one transaction with the inline projector; projections rebuild from the ledger, equal on both databases.
  A merged canonical ledger therefore yields the same state on every node without copying tables.
- **One stream per record with a version** (`stream_version`, `expected_version`): the base context a replayed
  command needs ("I changed this record at version 7").
- **A hash chain per scope** and a **sealed, signed archive** continuing it (`tl_core.archive`; `tl restore` into an
  empty SQLite or Postgres target). Moving a ledger between shapes today is seal → restore; `tl migrate` is not built.
- **Every event names actor, source, correlation, causation, `recorded_at` and `effective_at`**, so a merged event
  says which replica captured it, when and for whom, and a batch can be compensated by id.
- **Files are content-addressed**, so the same capture on two nodes is one object; reconciliation exists.
- **One command runner with resolved access** (ADR-0017 §7) already re-executes commands against current state for
  automation; replaying a replica's command as its owner with a base context is the same mechanism.
- **Outbox and signed webhooks** are `seq`-cursor based and replayable; confidentiality filters every read path.
- Not built: a persisted command (only events are stored), replica identity, local segment, sync, merge policies,
  conflicts, provisional numbering (`reserve_range` is a stub), upcasters, `effective_at` in projections, bundles.

## 3. Designed: what Phase 3 I5 adds (brief §22, contract §3)
| Piece | Design |
|---|---|
| Replica identity and scope | Registered node, certificate, owner, scope subscription, `sync.max_offline_days`; revocation quarantines pending commands; encryption at rest (P3-Q14) |
| Local ledger, two segments | **Mirror**: canonical events with their `seq` and hash. **Local**: `PendingCommand` rows (command id, HLC, `captured_at`, `effective_at`, base `seq` and versions, local hash chain); state = mirror + pending, rows shown `◌`. Changes the frozen `Ledger` and `UnitOfWork`: an ADR at wave 0 (R-P3-1) |
| Sync | Handshake (protocol, schema hash, skew) → pull (scope- and viewer-filtered) → rebase preview → push files by hash → push commands in order → merge → ack → conflicts to inboxes. Commands are replayed; events are never accepted verbatim |
| Outcomes | Accepted, Auto-merged, Conflict, Rejected, Quarantined; none silent; `Command.Rejected` carries the reason |
| Merge policies (`tl:merge`, generated data) | `append_only` (new records, results, movements, posts, links), `delta` (quantities), `add_wins` (sets), `scalar` (conflict unless `lww_effective`, `upstream_wins`, `replica_wins`), `transition` (re-evaluated; same target is a no-op), `numbering` (provisional key kept as alias), `natural_key` (duplicate → `Record.Merged` + `same as`) |
| Conflict review | `SyncConflict` records; base, mine, theirs per field; keep mine, keep theirs, merge fields, merge records; bulk; agents propose |
| Site node; tests | Embedded server on the LAN with multi-level sync, last and droppable (P3-Q1); convergence, idempotency, no lost writes, causal order; simulator `partition` |

## 4. The hard cases
- **Numbering.** Gap-free numbers are allocated on the authority. Offline records get a provisional key or a number
  from a reserved range (P3-Q8); the final key is assigned at merge and the alias must resolve everywhere (R-P3-17).
  Formal correspondence is drafted offline and issued online only.
- **Confidentiality.** A replica receives only what its owner may read; `restricted` and `privileged` never
  replicate; Legal is excluded by test. Filtered pulls leave chain gaps, so a replica verifies per-event hashes, not
  continuity (R-P3-3). A **site server serves many viewers**: it must hold the union of their scopes, pull as the
  node's identity and enforce the viewer locally with the same code. A security gate.
- **Signatures and sign-offs** are valid only over the merged hash: IWP release, certificates and dispositions happen
  online or are re-signed after merge.
- **Schema drift.** A command carries the schema hash; upstream upcasts or raises a "schema changed" conflict. No
  upcaster exists (R12, X15): build it before the first replica ships.
- **Time and clocks.** `effective_at` is device time, `recorded_at` acceptance; skew flagged at handshake; response
  and calibration clocks recompute from ledgered starts and survive a late merge.
- **Side effects** (webhooks, rules, enrichers, jobs, lake) run on the authority only; a merged batch fires them once
  with the replica in the source **(proposed rule)**. Guards a person can waive become conflicts, not rejections (R-P3-9).

## 5. Proposed: the shape as a configuration of one binary
1. **Node kinds as config:** `authority` (default), `site` (replica with users, upstream named), `device` (one owner).
   Same services, screens and confidentiality code everywhere; a `--node` setting and the `● online` / `◌ offline ·
   14 pending` status bar.
2. **Authority is a property of a scope.** A project names its authoritative node; an on-premises customer makes the
   site server the authority with no upstream and can later attach a central node (seal → restore → a ledgered
   `Scope.AuthorityChanged`). The protocol is the same; only the direction changes.
3. **Offline writability per record type** beside `tl:merge`: `tl:offline: none | draft_only | full`. `full` for field
   capture (welds, boltup, inspections, punch, toolcrib, scaffold tags, posts, thread messages); `draft_only` for
   correspondence, certificates, sign-offs and gap-free numbered types; `none` for settings, schema packages,
   accounts, integration configuration. The owner approves the table.
4. **Build order:** the `Ledger` ADR → persisted commands and local segment → sync → policies on the field types →
   conflict screen → site node. 5. **Project bundle** (§24.4) as the one tool to move a project between shapes.

Open for the owner: P3-Q1, P3-Q8, P3-Q14, Q18 (which sites, how long offline); authority per scope; the offline table.
